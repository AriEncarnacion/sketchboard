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
UID = "ipad-0f8e2b9c-4d1a-4e6b-9c3d-7a5f1e2d3c4b"


class FakeGemma:
    """Returns canned HTML. Records what it was asked so tests can assert on prompts."""

    model = "fake"
    calls: list[list[dict]] = []
    reply_html = DOC

    async def aclose(self): ...
    async def alive(self): return True
    async def has_model(self): return True

    async def chat(self, messages, **kw):
        self.calls.append(messages)
        return Reply(text=f"notes\n```html\n{self.reply_html}\n```", prompt_tokens=10, completion_tokens=20, seconds=0.1)


class FakeNango:
    """Stands in for nango.dev. `connected` flips once the fake user has authorized."""

    configured = True
    connected = False

    async def aclose(self): ...
    async def create_session(self, user_id):
        return {"connect_link": f"https://connect.nango.dev/?token=fake-{user_id}", "expires_at": "2026-01-01T00:00:00Z"}
    async def find_connection(self, user_id):
        return "conn-1" if self.connected else None
    async def github_user(self, connection_id):
        return {"login": "octocat", "avatar_url": "https://avatars.example/1", "name": "The Octocat"}


@pytest.fixture
def client(monkeypatch):
    fake = FakeGemma()
    fake.calls = []
    nango = FakeNango()
    nango.connected = False
    monkeypatch.setattr(main, "Gemma", lambda: fake)
    monkeypatch.setattr(main, "Nango", lambda: nango)
    monkeypatch.setattr(harness.render, "available", lambda: False)  # no Chromium in route tests
    with TestClient(main.app) as c:
        c.fake = fake  # type: ignore[attr-defined]
        c.nango = nango  # type: ignore[attr-defined]
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


def test_auth_session(client):
    r = client.post("/api/v1/auth/github/session", json={"user_id": UID})
    assert r.status_code == 200, r.text
    assert r.json()["connect_link"].startswith("https://connect.nango.dev/")
    assert client.post("/api/v1/auth/github/session", json={"user_id": "bad id!"}).status_code == 422
    assert client.post("/api/v1/auth/github/session", json={"user_id": "ipad-short"}).status_code == 422
    assert client.get("/api/v1/auth/github/me", params={"user_id": "ipad-short"}).status_code == 422
    client.nango.configured = False
    assert client.post("/api/v1/auth/github/session", json={"user_id": UID}).status_code == 503


def test_auth_me(client):
    assert client.get("/api/v1/auth/github/me", params={"user_id": UID}).json() == {"connected": False}
    client.nango.connected = True
    body = client.get("/api/v1/auth/github/me", params={"user_id": UID}).json()
    assert body["connected"] is True and body["login"] == "octocat" and body["avatar_url"]
