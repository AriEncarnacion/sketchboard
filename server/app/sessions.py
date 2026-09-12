"""Session store so follow-up edits can build on the last mockup.

In-memory cache backed by one JSON file per session in SESSIONS_DIR, so sessions
survive a harness restart (every deploy restarts it). A session id is chosen by the
client (any `[A-Za-z0-9._-]{1,64}` string); Slack uses the thread as the id.
"""

import base64
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config

SESSION_TTL_S = 24 * 3600
MAX_CACHED = 500


@dataclass
class Session:
    id: str
    sketch: bytes
    mime: str
    description: str
    format: str = "tablet"
    html: str = ""
    history: list[str] = field(default_factory=list)   # edit instructions, in order
    touched: float = field(default_factory=time.time)  # wall clock: survives restarts

    def to_json(self) -> dict:
        return {"id": self.id, "sketch_base64": base64.b64encode(self.sketch).decode(), "mime": self.mime,
                "description": self.description, "format": self.format, "html": self.html, "history": self.history,
                "touched": self.touched}

    @classmethod
    def from_json(cls, d: dict) -> "Session":
        return cls(id=d["id"], sketch=base64.b64decode(d["sketch_base64"]), mime=d["mime"],
                   description=d.get("description", ""), format=d.get("format", "tablet"), html=d.get("html", ""),
                   history=list(d.get("history", [])), touched=float(d.get("touched", time.time())))


_cache: dict[str, Session] = {}


def _dir() -> Path | None:
    if not config.SESSIONS_DIR:
        return None
    p = Path(config.SESSIONS_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(sid: str) -> Path | None:
    d = _dir()
    return d / f"{sid}.json" if d else None


def _save(s: Session) -> None:
    p = _path(s.id)
    if p is None:
        return
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(s.to_json()))
    tmp.replace(p)


def _load(sid: str) -> Session | None:
    p = _path(sid)
    if p is None or not p.exists():
        return None
    try:
        s = Session.from_json(json.loads(p.read_text()))
    except (ValueError, KeyError):
        return None
    if time.time() - s.touched > SESSION_TTL_S:
        p.unlink(missing_ok=True)
        return None
    return s


def _evict_cache() -> None:
    now = time.time()
    for sid in [s for s, v in _cache.items() if now - v.touched > SESSION_TTL_S]:
        del _cache[sid]
    while len(_cache) > MAX_CACHED:
        oldest = min(_cache.values(), key=lambda s: s.touched)
        del _cache[oldest.id]


def start(sid: str, sketch: bytes, mime: str, description: str, fmt: str = "tablet") -> Session:
    _evict_cache()
    s = Session(id=sid, sketch=sketch, mime=mime, description=description, format=fmt)
    _cache[sid] = s
    _save(s)
    return s


def get(sid: str) -> Session | None:
    s = _cache.get(sid) or _load(sid)
    if s:
        s.touched = time.time()
        _cache[sid] = s
    return s


def update_html(sid: str, html: str) -> None:
    s = get(sid)
    if s:
        s.html = html
        s.touched = time.time()
        _save(s)


def save(sid: str) -> None:
    """Persist whatever is in the cache for this session (e.g. after appending history)."""
    s = _cache.get(sid)
    if s:
        _save(s)
