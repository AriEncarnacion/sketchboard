"""Route-level tests with the model stubbed out. No GPU, no Chromium."""

import base64
import json

import pytest
from fastapi.testclient import TestClient

from app import harness, main
from app.gemma import Reply

DOC = "<!doctype html><html><body><h1>Login</h1><button>Go</button></body></html>"
DOC2 = DOC.replace("Go", "Blue Go")
IMG = base64.b64encode(b"\xff\xd8\xff\xe0 fake jpeg").decode()


class FakeGemma:
    """Returns canned HTML. Records what it was asked so tests can assert on prompts."""

    model = "fake"
    calls: list[list[dict]] = []
    reply_html = DOC
    reply_text: str | None = None   # when set, non-streaming chat() returns this verbatim

    async def aclose(self): ...
    async def alive(self): return True
    async def has_model(self): return True

    async def chat(self, messages, **kw):
        self.calls.append(messages)
        if self.reply_text is not None:
            return Reply(text=self.reply_text, prompt_tokens=10, completion_tokens=5, seconds=0.05)
        return Reply(text=f"notes\n```html\n{self.reply_html}\n```", prompt_tokens=10, completion_tokens=20, seconds=0.1)

    def chat_stream(self, messages, **kw):
        """Feeds the canned reply out in small pieces, like the real endpoint."""
        self.calls.append(messages)
        reply = Reply(text="")
        full = f"notes\n```html\n{self.reply_html}\n```"

        async def deltas():
            for i in range(0, len(full), 7):
                piece = full[i:i + 7]
                reply.text += piece
                yield piece
            reply.prompt_tokens, reply.completion_tokens, reply.seconds = 10, 20, 0.1

        return reply, deltas()


@pytest.fixture
def client(monkeypatch):
    fake = FakeGemma()
    fake.calls = []
    monkeypatch.setattr(main, "Gemma", lambda: fake)
    monkeypatch.setattr(harness.render, "available", lambda: False)  # no Chromium in route tests
    with TestClient(main.app) as c:
        c.fake = fake  # type: ignore[attr-defined]
        yield c


def events(resp):
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in resp.text.splitlines() if line]


def test_health_and_ready(client):
    assert client.get("/healthz").json()["api_version"] == 1
    assert client.get("/readyz").status_code == 200


def test_mockup_stream_shape(client):
    evs = events(client.post("/api/v1/mockup", json={"image_base64": IMG, "description": "login"}))
    types = [e["type"] for e in evs]
    assert types[0] == "session" and evs[0]["session_id"]
    assert "draft" in types and types[-1] == "final"
    assert evs[-1]["html"] == DOC and evs[-1]["chosen"] == 0


def test_client_chosen_session_id_and_edit(client):
    events(client.post("/api/v1/mockup", json={"image_base64": IMG, "session_id": "ipad-1"}))
    client.fake.reply_html = DOC2
    evs = events(client.post("/api/v1/edit", json={"session_id": "ipad-1", "instruction": "make the button blue"}))
    assert evs[0] == {"type": "session", "session_id": "ipad-1"}
    assert evs[-1]["type"] == "final" and evs[-1]["html"] == DOC2
    # The edit prompt carried the previous HTML and the instruction.
    prompt_text = client.fake.calls[-1][-1]["content"][0]["text"]
    assert DOC in prompt_text and "make the button blue" in prompt_text
    # Session now holds the edited html and the history.
    s = client.get("/api/v1/session/ipad-1").json()
    assert s["html"] == DOC2 and s["history"] == ["make the button blue"]


def test_edit_unknown_session(client):
    assert client.post("/api/v1/edit", json={"session_id": "nope", "instruction": "x"}).status_code == 404


def test_bad_input(client):
    assert client.post("/api/v1/mockup", json={"image_base64": "###"}).status_code == 400
    assert client.post("/api/v1/mockup", json={"image_base64": IMG, "session_id": "has space"}).status_code == 422
    assert client.post("/api/v1/mockup", json={"image_base64": IMG, "mime": "text/html"}).status_code == 422


def test_legacy_alias(client):
    assert events(client.post("/api/mockup", json={"image_base64": IMG}))[-1]["type"] == "final"


def test_draft_partials_stream_before_draft(client, monkeypatch):
    monkeypatch.setattr(harness, "PARTIAL_MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(harness, "PARTIAL_MIN_GROWTH", 1)
    evs = events(client.post("/api/v1/mockup", json={"image_base64": IMG}))
    types = [e["type"] for e in evs]
    partials = [e for e in evs if e["type"] == "draft_partial"]
    assert partials, types
    assert types.index("draft_partial") < types.index("draft")
    # Partials grow, each ends on a complete tag, and the last is a prefix of the full draft.
    lens = [p["chars"] for p in partials]
    assert lens == sorted(lens) and all(p["html"].endswith(">") for p in partials)
    assert DOC.startswith(partials[-1]["html"])
    assert evs[-1]["html"] == DOC


def test_stream_false_emits_no_partials(client):
    evs = events(client.post("/api/v1/mockup", json={"image_base64": IMG, "stream": False}))
    assert not [e for e in evs if e["type"] == "draft_partial"]
    assert evs[-1]["html"] == DOC


PATCH = "<<<<<<< SEARCH\n<button>Go</button>\n=======\n<button class=\"green\">Go</button>\n>>>>>>> REPLACE"
PATCHED = DOC.replace("<button>Go</button>", '<button class="green">Go</button>')


def test_edit_uses_patch_when_it_applies(client):
    events(client.post("/api/v1/mockup", json={"image_base64": IMG, "session_id": "p1"}))
    client.fake.reply_text = PATCH
    evs = events(client.post("/api/v1/edit", json={"session_id": "p1", "instruction": "make the button green"}))
    types = [e["type"] for e in evs]
    assert "patch" in types and "draft_partial" not in types   # fast path, no rewrite
    draft = next(e for e in evs if e["type"] == "draft")
    assert draft["patched"] is True and draft["html"] == PATCHED
    assert evs[-1]["html"] == PATCHED
    assert client.get("/api/v1/session/p1").json()["html"] == PATCHED
    # The patch prompt carried the current HTML and asked for SEARCH/REPLACE blocks.
    prompt_text = client.fake.calls[-1][-1]["content"][0]["text"]
    assert DOC in prompt_text and "<<<<<<< SEARCH" in prompt_text


def test_edit_falls_back_to_rewrite_when_patch_misses(client):
    events(client.post("/api/v1/mockup", json={"image_base64": IMG, "session_id": "p2"}))
    client.fake.reply_text = PATCH.replace("<button>Go</button>", "<button>Nope</button>")  # search won't match
    client.fake.reply_html = DOC2
    evs = events(client.post("/api/v1/edit", json={"session_id": "p2", "instruction": "x"}))
    msgs = [e.get("message", "") for e in evs if e["type"] == "status"]
    assert any("did not apply" in m for m in msgs)
    draft = next(e for e in evs if e["type"] == "draft")
    assert draft["patched"] is False and draft["html"] == DOC2   # rewrite path (streamed)
    assert evs[-1]["html"] == DOC2


def test_edit_patch_false_always_rewrites(client):
    events(client.post("/api/v1/mockup", json={"image_base64": IMG, "session_id": "p3"}))
    client.fake.reply_text = PATCH
    client.fake.reply_html = DOC2
    evs = events(client.post("/api/v1/edit", json={"session_id": "p3", "instruction": "x", "patch": False}))
    assert "patch" not in [e["type"] for e in evs]
    assert evs[-1]["html"] == DOC2
