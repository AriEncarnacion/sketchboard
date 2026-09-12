"""Sketchboard harness API. Contract: ../API.md

  GET  /healthz             process is up
  GET  /readyz              Ollama is up and has the model (503 otherwise)
  POST /api/v1/mockup       sketch + notes -> NDJSON event stream (see harness.py)
  POST /api/v1/edit         follow-up instruction on a session's last mockup -> same stream
  GET  /api/v1/session/{id} last html for a session (reconnect / debugging)

Runs behind nginx on the Lambda box; nginx does the bearer-token check.
"""

import base64
import binascii
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import config, harness, render, sessions
from .gemma import Gemma

API_VERSION = 1


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.gemma = Gemma()
    yield
    await app.state.gemma.aclose()
    await render.shutdown()


app = FastAPI(title="Sketchboard harness", version=str(API_VERSION), lifespan=lifespan)
v1 = APIRouter(prefix="/api/v1")

_SESSION_ID = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,64}$",
                    description="Client-chosen id. Omit to have the server mint one (see the `session` event).")


class MockupRequest(BaseModel):
    image_base64: str = Field(description="The sketch, base64 (no data: prefix)")
    mime: str = Field(default="image/jpeg", pattern=r"^image/(jpeg|png|webp)$")
    description: str = Field(default="", max_length=4000, description="Dictated notes from the user")
    session_id: str | None = _SESSION_ID
    max_iterations: int | None = Field(default=None, ge=0, le=5)
    model: str | None = Field(default=None, pattern=r"^[\w.:-]+$", description="Override the Ollama model tag")
    debug: bool = Field(default=False, description="Also stream render screenshots")


class EditRequest(BaseModel):
    session_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    instruction: str = Field(min_length=1, max_length=2000, description="e.g. 'make the button blue'")
    model: str | None = Field(default=None, pattern=r"^[\w.:-]+$")
    debug: bool = False


def _decode_image(b64: str) -> bytes:
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "image_base64 is not valid base64")
    if not data:
        raise HTTPException(400, "empty image")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "image larger than 20 MB")
    return data


def _ndjson(events: AsyncIterator[dict[str, Any]], sid: str) -> StreamingResponse:
    async def gen():
        try:
            async for ev in events:
                if ev.get("type") == "final":
                    sessions.update_html(sid, ev["html"])
                yield json.dumps(ev) + "\n"
        except Exception as e:  # noqa: BLE001 - surface to the client instead of a dropped stream
            yield json.dumps({"type": "error", "message": f"{e.__class__.__name__}: {e}"}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _prepend(first: dict[str, Any], rest: AsyncIterator[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
    yield first
    async for ev in rest:
        yield ev


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"ok": True, "api_version": API_VERSION, "model": config.MODEL, "render": render.available()}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    g: Gemma = app.state.gemma
    alive = await g.alive()
    has = alive and await g.has_model()
    body = {"ollama": alive, "model": config.MODEL, "model_loaded": has, "render": render.available(),
            "api_version": API_VERSION}
    return JSONResponse(body, status_code=200 if has else 503)


@v1.post("/mockup")
async def mockup(req: MockupRequest) -> StreamingResponse:
    sketch = _decode_image(req.image_base64)
    sid = req.session_id or uuid.uuid4().hex[:16]
    sessions.start(sid, sketch, req.mime, req.description)
    events = harness.run(app.state.gemma, sketch, req.mime, req.description,
                         max_iterations=req.max_iterations, model=req.model, debug=req.debug)
    return _ndjson(_prepend({"type": "session", "session_id": sid}, events), sid)


@v1.post("/edit")
async def edit(req: EditRequest) -> StreamingResponse:
    s = sessions.get(req.session_id)
    if s is None or not s.html:
        raise HTTPException(404, "unknown session or no mockup yet; call /api/v1/mockup first")
    s.history.append(req.instruction.strip())
    events = harness.edit(app.state.gemma, s.sketch, s.mime, s.description, s.html, req.instruction,
                          s.history[:-1], model=req.model, debug=req.debug)
    return _ndjson(_prepend({"type": "session", "session_id": s.id}, events), s.id)


@v1.get("/session/{session_id}")
async def session(session_id: str) -> dict[str, Any]:
    s = sessions.get(session_id)
    if s is None:
        raise HTTPException(404, "unknown session")
    return {"session_id": s.id, "description": s.description, "html": s.html, "history": s.history}


app.include_router(v1)

# Unversioned alias from the first scaffold; remove once the app is on /api/v1.
app.add_api_route("/api/mockup", mockup, methods=["POST"], include_in_schema=False)
