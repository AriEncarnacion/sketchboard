# Sketchboard in Discord

Same shape as the Slack bot: post a sketch, get a mockup in a thread, reply to change it.
A sidecar on the GPU box that talks to the harness over localhost. The Discord gateway is
an outbound websocket, so nothing inbound is needed.

```
image in channel ──┐
/sketch image: ────┼─► bot ─► POST /api/v1/mockup ─► thread: PNG + link
reply in thread ───┘        POST /api/v1/edit    ─► thread: updated PNG
```

The thread is the session: a thread opened on a message shares that message's id, so
`discord-<thread id>` is the harness session id and the bot keeps no state.

## Create the Discord app (once, ~5 min, needs a server where you can add bots)

1. https://discord.com/developers/applications → **New Application** → name it Sketchboard.
2. **Bot** tab → **Reset Token** → copy it: that's `DISCORD_BOT_TOKEN`.
   On the same tab, under *Privileged Gateway Intents*, turn on **Message Content Intent**.
   Without it the bot sees images but not captions or thread replies.
3. **OAuth2** tab → *URL Generator*: scopes `bot` and `applications.commands`; bot
   permissions **Send Messages**, **Send Messages in Threads**, **Create Public Threads**,
   **Attach Files**, **Embed Links**, **Read Message History**. Open the generated URL and
   add the bot to your server.
4. Put the token in `lambda/.env`:
   ```
   DISCORD_BOT_TOKEN=…
   ```
5. Deploy the server (viewer route + on-disk sessions) if you haven't, then the bot:
   ```bash
   lambda/lambdactl.sh deploy
   lambda/lambdactl.sh deploy-discord
   ```
   The `/sketch` command registers globally on startup; Discord can take up to an hour to
   show a new global command in every server. Posting an image works immediately.

## Using it

- **Whiteboard photo:** post an image in a text channel with a message like
  "checkout screen, apple pay on top". The bot opens a thread on it and replies there in ~30 s.
- **`/sketch`:** pick the image, add notes. The bot posts your sketch in the channel, opens a
  thread, and works there.
- **Change it:** reply in the thread in plain English. Each reply applies to the latest version.
- **Share it:** every result carries an "Open the live mockup" link that works in any browser.

Set `DISCORD_REQUIRE_MENTION=1` in `lambda/.env` for busy servers: images are only picked
up when the message mentions @Sketchboard.

## Debugging

```bash
lambda/lambdactl.sh ssh sudo journalctl -u sketchboard-discord -f
```

- Bot online but ignores captions/replies: Message Content Intent is off in the portal.
- `Missing Permissions` on thread creation: re-invite with the permissions above.
- `/sketch` not showing: global command propagation; wait, or restart the Discord client.

## Local run

```bash
cd discordbot && uv venv && uv pip install -r requirements.txt
ssh -L 8000:127.0.0.1:8000 ubuntu@<box-ip>     # tunnel to the harness, in another terminal
DISCORD_BOT_TOKEN=… .venv/bin/python bot.py
```
