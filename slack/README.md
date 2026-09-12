# Sketchboard in Slack

Post a sketch, get a mockup in the thread, reply to change it. The bot is a sidecar on the
GPU box that talks to the harness over localhost; it never touches the model directly.

```
photo in channel ──┐
/sketch modal ─────┼─► bot ─► POST /api/v1/mockup ─► PNG + link in thread
reply in thread ───┘        POST /api/v1/edit    ─► updated PNG in thread
```

The Slack thread is the session: its id is derived from the channel and root timestamp,
so the bot keeps no state and survives restarts. Sessions live on disk on the box.

## Create the Slack app (once, ~5 min, needs a workspace you can install apps to)

1. https://api.slack.com/apps → **Create New App** → **From a manifest** → pick the workspace
   → paste `slack/manifest.json` → Create.
2. **Basic Information → App-Level Tokens** → Generate a token with scope
   `connections:write`. Copy it: that's `SLACK_APP_TOKEN` (`xapp-…`).
3. **Install App** → Install to Workspace → allow. Copy the **Bot User OAuth Token**:
   that's `SLACK_BOT_TOKEN` (`xoxb-…`).
4. Put both in `lambda/.env`:
   ```
   SLACK_BOT_TOKEN=xoxb-…
   SLACK_APP_TOKEN=xapp-…
   ```
5. Deploy the server (it needs the viewer route and on-disk sessions) and the bot:
   ```bash
   lambda/lambdactl.sh deploy
   lambda/lambdactl.sh deploy-slack
   ```
6. In Slack, invite the bot to a channel: `/invite @Sketchboard`.

No inbound URL is needed: Socket Mode dials out from the box.

## Using it

- **Whiteboard photo:** post an image in the channel with a caption like
  "checkout screen, apple pay on top". The bot replies in the thread within ~30 s.
- **`/sketch`:** opens a form with a file picker (camera on the phone) and a notes field.
  The bot posts a root message in the channel and replies in its thread.
- **Change it:** reply in the thread with plain English. "make the button green",
  "add a sign in with apple button under it". Each reply is applied to the latest version.
- **Share it:** every result carries an "Open the live mockup" link that renders the HTML
  in any browser, no Slack needed.

Set `SLACK_REQUIRE_MENTION=1` in `lambda/.env` if the bot is in a busy channel and should
only pick up images when `@Sketchboard` is mentioned.

## Debugging

```bash
lambda/lambdactl.sh ssh sudo journalctl -u sketchboard-slack -f
```

Common failures:
- `not_in_channel`: invite the bot to the channel.
- `:warning: unsupported image type`: HEIC from an iPhone. Slack usually converts to JPEG;
  if not, the Photos app can export JPEG.
- No reply at all: the bot only sees channels it's in, and only top-level images. Check
  the journal for the event.

## Local run

```bash
cd slack && uv venv && uv pip install -r requirements.txt
SLACK_BOT_TOKEN=… SLACK_APP_TOKEN=… HARNESS_URL=http://<box-ip>:8080 .venv/bin/python bot.py
```
Pointing `HARNESS_URL` at the public port needs the bearer token, which the bot doesn't
send; for local runs tunnel instead: `ssh -L 8000:127.0.0.1:8000 ubuntu@<box-ip>`.
