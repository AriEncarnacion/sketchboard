"""Sketchboard harness API.

  GET  /healthz            process is up
  GET  /readyz             Ollama is up and has the model
  POST /api/mockup         sketch + notes -> stream of NDJSON events (see harness.py)

Runs behind nginx on the Lambda box; nginx does the bearer-token check.
"""

import base64
import binascii
import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import config, harness, render
from .gemma import Gemma


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.gemma = Gemma()
    yield
    await app.state.gemma.aclose()
    await render.shutdown()


app = FastAPI(title="Sketchboard harness", lifespan=lifespan)


class MockupRequest(BaseModel):
    image_base64: str = Field(description="The sketch, base64 (no data: prefix)")
    mime: str = Field(default="image/jpeg", pattern=r"^image/(jpeg|png|webp)$")
    description: str = Field(default="", max_length=4000, description="Dictated notes from the user")
    max_iterations: int | None = Field(default=None, ge=0, le=5)
    debug: bool = Field(default=False, description="Also stream render screenshots")


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"ok": True, "model": config.MODEL, "render": render.available()}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    g: Gemma = app.state.gemma
    alive = await g.alive()
    has = alive and await g.has_model()
    body = {"ollama": alive, "model": config.MODEL, "model_loaded": has, "render": render.available()}
    return JSONResponse(body, status_code=200 if has else 503)


@app.post("/api/mockup")
async def mockup(req: MockupRequest) -> StreamingResponse:
    try:
        sketch = base64.b64decode(req.image_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "image_base64 is not valid base64")
    if not sketch:
        raise HTTPException(400, "empty image")
    if len(sketch) > 20 * 1024 * 1024:
        raise HTTPException(413, "image larger than 20 MB")

    async def events():
        try:
            async for ev in harness.run(
                app.state.gemma, sketch, req.mime, req.description,
                max_iterations=req.max_iterations, debug=req.debug,
            ):
                yield json.dumps(ev) + "\n"
        except Exception as e:  # noqa: BLE001 - surface to the client instead of a dropped stream
            yield json.dumps({"type": "error", "message": f"{e.__class__.__name__}: {e}"}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
