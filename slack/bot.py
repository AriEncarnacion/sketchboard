"""Sketchboard Slack bot: sketch in, mockup out, the thread is the session.

Ways in:
  * Post an image in a channel the bot is in (caption = notes)  -> mockup in the thread
  * /sketch                                                      -> modal: photo/file + notes
  * Reply in a mockup thread ("make the button green")          -> edited mockup in the thread

Runs on the GPU box next to the harness and talks to it on localhost (no bearer needed;
nginx only guards the public port). Socket Mode: the bot dials out to Slack, so no
inbound port, no TLS, no public URL. Setup and scopes: slack/README.md, slack/manifest.json.
"""

import io
import json
import logging
import os
import re
import time
from typing import Any

import httpx
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

log = logging.getLogger("sketchboard.slack")

HARNESS = os.environ.get("HARNESS_URL", "http://127.0.0.1:8000").rstrip("/")
REQUIRE_MENTION = os.environ.get("SLACK_REQUIRE_MENTION", "0") == "1"
MAX_ITERATIONS = int(os.environ.get("MAX_ITERATIONS", "2"))
IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}

app = App(token=os.environ.get("SLACK_BOT_TOKEN", "xoxb-unset"), token_verification_enabled=False)
http = httpx.Client(timeout=httpx.Timeout(900, connect=10))
_bot_user_id: str | None = None


# --- helpers ------------------------------------------------------------------------

def session_id(channel: str, thread_ts: str) -> str:
    """Deterministic id from the thread, so no state lives in the bot."""
    return f"slack-{channel}-{thread_ts.replace('.', '-')}"


def strip_mentions(text: str) -> str:
    return re.sub(r"<@[A-Z0-9]+>", "", text or "").strip()


def is_image(f: dict[str, Any]) -> bool:
    return (f.get("mimetype") or "").lower() in IMAGE_MIMES


def download(client, f: dict[str, Any]) -> tuple[bytes, str]:
    """Bytes + mime of a Slack file. Refetches file info when the event didn't carry a URL."""
    url = f.get("url_private_download") or f.get("url_private")
    mime = (f.get("mimetype") or "").lower()
    if not url or not mime:
        info = client.files_info(file=f["id"])["file"]
        url = info.get("url_private_download") or info["url_private"]
        mime = (info.get("mimetype") or "").lower()
    r = httpx.get(url, headers={"Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}"},
                  follow_redirects=True, timeout=60)
    r.raise_for_status()
    if mime not in IMAGE_MIMES:
        raise ValueError(f"unsupported image type {mime or 'unknown'}; use a JPEG or PNG")
    return r.content, mime


def harness_stream(path: str, body: dict[str, Any]):
    with http.stream("POST", f"{HARNESS}{path}", json=body) as r:
        if r.status_code != 200:
            r.read()
            raise RuntimeError(f"harness {r.status_code}: {r.text[:200]}")
        for line in r.iter_lines():
            if line.strip():
                yield json.loads(line)


def session_exists(sid: str) -> bool:
    r = http.get(f"{HARNESS}/api/v1/session/{sid}", timeout=10)
    return r.status_code == 200 and bool(r.json().get("html"))


def quote(text: str, limit: int = 600) -> str:
    text = text.strip()
    if len(text) > limit:
        text = text[:limit] + "…"
    return "\n".join("> " + l for l in text.splitlines())


# --- the two jobs ---------------------------------------------------------------------

def run_mockup(client, channel: str, thread_ts: str, sketch: bytes, mime: str, notes: str) -> None:
    sid = session_id(channel, thread_ts)
    status = client.chat_postMessage(channel=channel, thread_ts=thread_ts, text="Drafting a mockup from your sketch…")
    update = lambda text: client.chat_update(channel=channel, ts=status["ts"], text=text)  # noqa: E731
    t0 = time.time()
    final = None
    try:
        body = {"image_base64": _b64(sketch), "mime": mime, "description": notes, "session_id": sid,
                "stream": False, "max_iterations": MAX_ITERATIONS}
        for ev in harness_stream("/api/v1/mockup", body):
            t = ev["type"]
            if t == "draft":
                update(f"Draft {ev['iteration']} ready in {ev['seconds']} s. Checking it against the sketch…")
            elif t == "verdict":
                update("The judge wants changes, revising…\n" + quote(ev.get("problems", "")))
            elif t == "approved":
                update("Approved by the judge. Rendering…")
            elif t == "final":
                final = ev
            elif t == "error":
                raise RuntimeError(ev.get("message", "unknown error"))
    except Exception as e:  # noqa: BLE001
        log.exception("mockup failed")
        update(f":warning: Couldn't make a mockup: {e}")
        return
    if final is None:
        update(":warning: The harness ended without a result.")
        return
    post_result(client, channel, thread_ts, sid, status["ts"], final, time.time() - t0, "Mockup")


def run_edit(client, channel: str, thread_ts: str, instruction: str) -> None:
    sid = session_id(channel, thread_ts)
    status = client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=f"Applying “{instruction}”…")
    update = lambda text: client.chat_update(channel=channel, ts=status["ts"], text=text)  # noqa: E731
    t0 = time.time()
    final = None
    try:
        for ev in harness_stream("/api/v1/edit", {"session_id": sid, "instruction": instruction, "stream": False}):
            t = ev["type"]
            if t == "patch":
                update(f"Patched {ev.get('hunks', '?')} place(s) in {ev.get('seconds', '?')} s. Rendering…")
            elif t == "final":
                final = ev
            elif t == "error":
                raise RuntimeError(ev.get("message", "unknown error"))
    except Exception as e:  # noqa: BLE001
        log.exception("edit failed")
        update(f":warning: Couldn't apply that: {e}")
        return
    if final is None:
        update(":warning: The harness ended without a result.")
        return
    post_result(client, channel, thread_ts, sid, status["ts"], final, time.time() - t0, "Updated mockup")


def post_result(client, channel, thread_ts, sid, status_ts, final, elapsed, verb) -> None:
    png = http.get(f"{HARNESS}/api/v1/session/{sid}/render.png", timeout=60).content
    info = http.get(f"{HARNESS}/api/v1/session/{sid}", timeout=10).json()
    link = info.get("viewer_url")
    how = "approved by the judge" if final.get("approved") else f"best of {int(final.get('iterations', 0)) + 1} drafts"
    lines = [f"*{verb}* ready in {elapsed:.0f} s, {how}."]
    if link:
        lines.append(f"<{link}|Open the live mockup>")
    lines.append("Reply in this thread to change it, e.g. _make the button green_.")
    client.files_upload_v2(channel=channel, thread_ts=thread_ts, file=io.BytesIO(png), filename="mockup.png",
                           title=verb, initial_comment="\n".join(lines))
    try:
        client.chat_delete(channel=channel, ts=status_ts)
    except Exception:  # noqa: BLE001 - progress message is cosmetic
        pass


def _b64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode()


# --- Slack entry points ------------------------------------------------------------------

@app.event("message")
def on_message(event, client, logger):
    if event.get("bot_id") or event.get("user") == _bot_user_id:
        return
    if event.get("subtype") not in (None, "file_share"):
        return  # edits, deletes, joins, ...
    channel, ts = event["channel"], event["ts"]
    thread_ts = event.get("thread_ts")
    text = strip_mentions(event.get("text", ""))
    images = [f for f in event.get("files", []) if is_image(f)]
    mentioned = bool(_bot_user_id and f"<@{_bot_user_id}>" in (event.get("text") or ""))

    if images and (thread_ts is None or thread_ts == ts):
        # A new sketch. Optionally only when the bot is mentioned (busy channels).
        if REQUIRE_MENTION and not mentioned:
            return
        try:
            sketch, mime = download(client, images[0])
        except ValueError as e:
            client.chat_postMessage(channel=channel, thread_ts=ts, text=f":warning: {e}")
            return
        run_mockup(client, channel, ts, sketch, mime, text)
    elif thread_ts and thread_ts != ts and text and not images:
        # A reply in a thread. Only act if this thread has a mockup.
        if session_exists(session_id(channel, thread_ts)):
            run_edit(client, channel, thread_ts, text)
        elif mentioned:
            client.chat_postMessage(channel=channel, thread_ts=thread_ts,
                                    text="No mockup in this thread yet. Post a sketch image, or use `/sketch`.")


@app.event("app_mention")
def on_mention(event, client):
    # The message handler covers mentions with images and thread replies; this is the
    # "what do you do?" case: a top-level mention with no image.
    if event.get("files") or event.get("thread_ts"):
        return
    client.chat_postMessage(channel=event["channel"], thread_ts=event["ts"],
                            text="Post a sketch as an image (a whiteboard photo works) with a line of notes, "
                                 "or type `/sketch`. I'll reply in the thread with a mockup; reply there to change it.")


@app.command("/sketch")
def open_sketch_modal(ack, body, client):
    ack()
    client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal", "callback_id": "sketch_modal",
            "private_metadata": json.dumps({"channel": body.get("channel_id")}),
            "title": {"type": "plain_text", "text": "Sketch to mockup"},
            "submit": {"type": "plain_text", "text": "Generate"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {"type": "input", "block_id": "file",
                 "label": {"type": "plain_text", "text": "Sketch (photo of a whiteboard, napkin, or a drawing)"},
                 "element": {"type": "file_input", "action_id": "file",
                             "filetypes": ["png", "jpg", "jpeg", "webp"], "max_files": 1}},
                {"type": "input", "block_id": "notes", "optional": True,
                 "label": {"type": "plain_text", "text": "Notes"},
                 "element": {"type": "plain_text_input", "action_id": "notes", "multiline": True,
                             "placeholder": {"type": "plain_text",
                                             "text": "login screen, photo on the left, sign in with apple and google"}}},
            ],
        },
    )


@app.view("sketch_modal")
def on_sketch_submit(ack, body, view, client):
    ack()
    channel = json.loads(view.get("private_metadata") or "{}").get("channel")
    user = body["user"]["id"]
    values = view["state"]["values"]
    files = values["file"]["file"].get("files") or []
    notes = (values["notes"]["notes"].get("value") or "").strip()
    if not channel or not files:
        return
    try:
        sketch, mime = download(client, files[0])
        root = client.chat_postMessage(
            channel=channel,
            text=f"<@{user}> asked for a mockup" + (f": _{notes}_" if notes else "") + " (sketch attached below)")
    except Exception as e:  # noqa: BLE001
        log.exception("modal submit failed")
        try:
            client.chat_postEphemeral(channel=channel, user=user,
                                      text=f":warning: {e}. If I'm not in this channel yet, `/invite` me first.")
        except Exception:  # noqa: BLE001
            pass
        return
    client.files_upload_v2(channel=channel, thread_ts=root["ts"], file=io.BytesIO(sketch),
                           filename="sketch." + ("png" if mime == "image/png" else "jpg"), title="Sketch")
    run_mockup(client, channel, root["ts"], sketch, mime, notes)


def main() -> None:
    global _bot_user_id
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for k in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"):
        if not os.environ.get(k):
            raise SystemExit(f"{k} is not set")
    _bot_user_id = app.client.auth_test()["user_id"]
    log.info("bot user %s, harness %s, require_mention=%s", _bot_user_id, HARNESS, REQUIRE_MENTION)
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    main()
