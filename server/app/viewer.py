"""Share a mockup outside the app: a signed, public viewer page plus a PNG render.

  GET /m/{session_id}?t=<sig>          the session's current HTML as a page (no bearer;
                                       nginx passes /m/ through). The signature keeps
                                       ids from being enumerable.
  GET /api/v1/session/{id}/render.png  screenshot of the current HTML at iPad size
                                       (bearer-gated like the rest of /api/).

`viewer_url(sid)` builds the signed link; the session endpoint includes it.
"""

import hmac
import hashlib

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from . import config, render, sessions

router = APIRouter()


def sign(sid: str) -> str:
    return hmac.new(config.VIEWER_SECRET.encode(), sid.encode(), hashlib.sha256).hexdigest()[:20]


def viewer_url(sid: str) -> str | None:
    if not config.PUBLIC_BASE_URL:
        return None
    return f"{config.PUBLIC_BASE_URL}/m/{sid}?t={sign(sid)}"


@router.get("/m/{session_id}", response_class=HTMLResponse)
async def view(session_id: str, t: str = Query(default="")) -> HTMLResponse:
    if not hmac.compare_digest(t, sign(session_id)):
        raise HTTPException(404, "not found")
    s = sessions.get(session_id)
    if s is None or not s.html:
        raise HTTPException(404, "no mockup for this session")
    return HTMLResponse(s.html, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


@router.get("/api/v1/session/{session_id}/render.png")
async def render_png(session_id: str) -> Response:
    s = sessions.get(session_id)
    if s is None or not s.html:
        raise HTTPException(404, "no mockup for this session")
    if not render.available():
        raise HTTPException(503, "renderer unavailable")
    png = await render.screenshot(s.html)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})
