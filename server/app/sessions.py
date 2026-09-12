"""In-memory session store so follow-up edits can build on the last mockup.

Good enough for the hackathon: one process, a few hundred sessions, evicted after
SESSION_TTL_S of inactivity. A session id is chosen by the client (any string ≤ 64 chars).
"""

import time
from dataclasses import dataclass, field

SESSION_TTL_S = 6 * 3600
MAX_SESSIONS = 500


@dataclass
class Session:
    id: str
    sketch: bytes
    mime: str
    description: str
    html: str = ""
    history: list[str] = field(default_factory=list)   # edit instructions, in order
    touched: float = field(default_factory=time.monotonic)


_sessions: dict[str, Session] = {}


def _evict() -> None:
    now = time.monotonic()
    for sid in [s for s, v in _sessions.items() if now - v.touched > SESSION_TTL_S]:
        del _sessions[sid]
    while len(_sessions) > MAX_SESSIONS:
        oldest = min(_sessions.values(), key=lambda s: s.touched)
        del _sessions[oldest.id]


def start(sid: str, sketch: bytes, mime: str, description: str) -> Session:
    _evict()
    s = Session(id=sid, sketch=sketch, mime=mime, description=description)
    _sessions[sid] = s
    return s


def get(sid: str) -> Session | None:
    s = _sessions.get(sid)
    if s:
        s.touched = time.monotonic()
    return s


def update_html(sid: str, html: str) -> None:
    s = _sessions.get(sid)
    if s:
        s.html = html
        s.touched = time.monotonic()
