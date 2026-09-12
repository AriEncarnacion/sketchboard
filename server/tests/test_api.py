"""Route-level tests with the model stubbed out. No GPU, no Chromium."""

import base64
import json

import pytest
from fastapi.testclient import TestClient

from app import harness, main
from app.gemma import Reply

DOC = "<!doctype html><html><body><h1>Login</h1><button>Go</button></body></html>"
DOC2 = DOC.replace("Go", "Blue Go")
from app import basecss  # noqa: E402
FULL, FULL2 = basecss.inject(DOC), basecss.inject(DOC2)   # what the API returns: base CSS injected
IMG = base64.b64encode(b"\xff\xd8\xff\xe0 fake jpeg").decode()
UID = "ipad-0f8e2b9c-4d1a-4e6b-9c3d-7a5f1e2d3c4b"


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
    assert evs[-1]["html"] == FULL and evs[-1]["chosen"] == 0


def test_client_chosen_session_id_and_edit(client):
    events(client.post("/api/v1/mockup", json={"image_base64": IMG, "session_id": "ipad-1"}))
    client.fake.reply_html = DOC2
    evs = events(client.post("/api/v1/edit", json={"session_id": "ipad-1", "instruction": "make the button blue"}))
    assert evs[0] == {"type": "session", "session_id": "ipad-1"}
    assert evs[-1]["type"] == "final" and evs[-1]["html"] == FULL2
    # The edit prompt carried the previous HTML and the instruction.
    prompt_text = client.fake.calls[-1][-1]["content"][0]["text"]
    assert "<h1>Login</h1>" in prompt_text and "make the button blue" in prompt_text
    # Session now holds the edited html and the history.
    s = client.get("/api/v1/session/ipad-1").json()
    assert s["html"] == FULL2 and s["history"] == ["make the button blue"]


def test_edit_unknown_session(client):
    assert client.post("/api/v1/edit", json={"session_id": "nope", "instruction": "x"}).status_code == 404


def test_bad_input(client):
    assert client.post("/api/v1/mockup", json={"image_base64": "###"}).status_code == 400
    assert client.post("/api/v1/mockup", json={"image_base64": IMG, "session_id": "has space"}).status_code == 422
    assert client.post("/api/v1/mockup", json={"image_base64": IMG, "mime": "text/html"}).status_code == 422


def test_viewer_link_and_page(client, monkeypatch):
    from app import config, viewer
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "http://box:8080")
    events(client.post("/api/v1/mockup", json={"image_base64": IMG, "session_id": "share-1"}))
    info = client.get("/api/v1/session/share-1").json()
    assert info["viewer_url"] == f"http://box:8080/m/share-1?t={viewer.sign('share-1')}"
    # Wrong or missing signature is a 404, right one serves the HTML.
    assert client.get("/m/share-1").status_code == 404
    assert client.get("/m/share-1?t=deadbeef").status_code == 404
    r = client.get(f"/m/share-1?t={viewer.sign('share-1')}")
    assert r.status_code == 200 and "<h1>Login</h1>" in r.text   # base CSS gets injected, so not byte-equal
    assert r.headers["content-type"].startswith("text/html")
    # PNG render needs Chromium, which route tests stub out.
    assert client.get("/api/v1/session/share-1/render.png").status_code == 503
    assert client.get("/api/v1/session/nope/render.png").status_code == 404


def test_legacy_alias(client):
    assert events(client.post("/api/mockup", json={"image_base64": IMG}))[-1]["type"] == "final"


def test_draft_partials_stream_before_draft(client, monkeypatch):
    monkeypatch.setattr(harness, "PARTIAL_MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(harness, "PARTIAL_MIN_GROWTH", 1)
    client.fake.reply_html = '<div class="screen"><h1>Login</h1><button class="btn">Go</button></div>'
    evs = events(client.post("/api/v1/mockup", json={"image_base64": IMG}))
    types = [e["type"] for e in evs]
    partials = [e for e in evs if e["type"] == "draft_partial"]
    assert partials, types
    assert types.index("draft_partial") < types.index("draft")
    # Partials grow, each is a complete wrapped document, and each is a prefix of the
    # final document once the closing tags the wrapper adds are removed.
    lens = [p["chars"] for p in partials]
    final = evs[-1]["html"]
    assert lens == sorted(lens) and all(p["html"].endswith("</body></html>") for p in partials)
    assert all(final.startswith(p["html"][: -len("</body></html>")]) for p in partials)
    assert final.endswith(client.fake.reply_html + "</body></html>")


def test_stream_false_emits_no_partials(client):
    evs = events(client.post("/api/v1/mockup", json={"image_base64": IMG, "stream": False}))
    assert not [e for e in evs if e["type"] == "draft_partial"]
    assert evs[-1]["html"] == FULL


PATCH = "<<<<<<< SEARCH\n<button>Go</button>\n=======\n<button class=\"green\">Go</button>\n>>>>>>> REPLACE"
PATCHED = DOC.replace("<button>Go</button>", '<button class="green">Go</button>')
FULLP = basecss.inject(PATCHED)


def test_edit_uses_patch_when_it_applies(client):
    events(client.post("/api/v1/mockup", json={"image_base64": IMG, "session_id": "p1"}))
    client.fake.reply_text = PATCH
    evs = events(client.post("/api/v1/edit", json={"session_id": "p1", "instruction": "make the button green"}))
    types = [e["type"] for e in evs]
    assert "patch" in types and "draft_partial" not in types   # fast path, no rewrite
    draft = next(e for e in evs if e["type"] == "draft")
    assert draft["patched"] is True and draft["html"] == FULLP
    assert evs[-1]["html"] == FULLP
    assert client.get("/api/v1/session/p1").json()["html"] == FULLP
    # The patch prompt carried the current HTML and asked for SEARCH/REPLACE blocks.
    prompt_text = client.fake.calls[-1][-1]["content"][0]["text"]
    assert "<h1>Login</h1>" in prompt_text and "<<<<<<< SEARCH" in prompt_text


def test_edit_falls_back_to_rewrite_when_patch_misses(client):
    events(client.post("/api/v1/mockup", json={"image_base64": IMG, "session_id": "p2"}))
    client.fake.reply_text = PATCH.replace("<button>Go</button>", "<button>Nope</button>")  # search won't match
    client.fake.reply_html = DOC2
    evs = events(client.post("/api/v1/edit", json={"session_id": "p2", "instruction": "x"}))
    msgs = [e.get("message", "") for e in evs if e["type"] == "status"]
    assert any("did not apply" in m for m in msgs)
    draft = next(e for e in evs if e["type"] == "draft")
    assert draft["patched"] is False and draft["html"] == FULL2   # rewrite path (streamed)
    assert evs[-1]["html"] == FULL2


def test_edit_patch_false_always_rewrites(client):
    events(client.post("/api/v1/mockup", json={"image_base64": IMG, "session_id": "p3"}))
    client.fake.reply_text = PATCH
    client.fake.reply_html = DOC2
    evs = events(client.post("/api/v1/edit", json={"session_id": "p3", "instruction": "x", "patch": False}))
    assert "patch" not in [e["type"] for e in evs]
    assert evs[-1]["html"] == FULL2


FRAG = '<div class="screen"><button class="btn btn-primary">Go</button></div>'


def test_fragment_reply_is_wrapped_with_base_css(client):
    from app import basecss
    client.fake.reply_html = FRAG
    evs = events(client.post("/api/v1/mockup", json={"image_base64": IMG, "session_id": "f1"}))
    final = evs[-1]["html"]
    assert final.startswith("<!doctype html>") and basecss.STYLE_ID in final and FRAG in final
    # Partials are wrapped too, so the app always gets a renderable document.
    assert all(basecss.STYLE_ID in e["html"] for e in evs if e["type"] == "draft_partial")
    # The system prompt carried the class guide.
    assert "LAYOUT" in client.fake.calls[0][0]["content"]


def test_edit_prompt_shows_collapsed_base_css(client):
    from app import basecss
    client.fake.reply_html = FRAG
    events(client.post("/api/v1/mockup", json={"image_base64": IMG, "session_id": "f2"}))
    client.fake.reply_text = "<<<<<<< SEARCH\n<button class=\"btn btn-primary\">Go</button>\n=======\n<button class=\"btn btn-danger\">Go</button>\n>>>>>>> REPLACE"
    evs = events(client.post("/api/v1/edit", json={"session_id": "f2", "instruction": "make it red"}))
    prompt_text = client.fake.calls[-1][-1]["content"][0]["text"]
    assert basecss.PLACEHOLDER in prompt_text and ".btn-primary{" not in prompt_text
    final = evs[-1]["html"]
    assert "btn-danger" in final and ".btn-primary{" in final   # patched, and base CSS restored
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


def test_layout_report_flags_narrow_column():
    from app.render import LayoutReport
    narrow = LayoutReport(element_count=20, content_width=360, viewport_width=1180)
    assert not narrow.clean
    assert "360px of the 1180px" in narrow.summary(1180, 820)
    wide = LayoutReport(element_count=20, content_width=1100, viewport_width=1180)
    assert wide.clean and wide.summary(1180, 820) == ""
    unmeasured = LayoutReport(element_count=20)   # render disabled: no width facts, not a problem
    assert unmeasured.clean


def test_format_detection_and_events(client):
    from app import formats
    assert formats.detect("a mobile app for kids") == "phone"
    assert formats.detect("web app dashboard") == "desktop"
    assert formats.detect("iPad landscape, but a mobile feel") == "tablet"   # explicit device wins
    assert formats.detect("login screen") == "tablet"
    evs = events(client.post("/api/v1/mockup", json={"image_base64": IMG, "description": "mobile app", "max_iterations": 0}))
    final = [e for e in evs if e["type"] == "final"][0]
    assert (final["format"], final["width"], final["height"]) == ("phone", 390, 844)
    evs = events(client.post("/api/v1/mockup", json={"image_base64": IMG, "description": "mobile app", "format": "desktop", "max_iterations": 0}))
    assert [e for e in evs if e["type"] == "final"][0]["width"] == 1440
