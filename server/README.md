# Sketchboard harness

FastAPI service that sits between the iPad app and Gemma. It takes a sketch plus dictated
notes, asks Gemma for an HTML mockup, renders it in headless Chromium, shows Gemma the
screenshot next to the sketch, and lets it revise. Up to `MAX_ITERATIONS` passes, then
returns the best draft. Every step streams to the client as it happens.

Runs on the Lambda box next to Ollama. nginx (port 8080) does the bearer-token check and
forwards `/api/` here and `/v1/` straight to Ollama.

## API

`POST /api/mockup` with JSON:

```json
{
  "image_base64": "<jpeg or png, base64>",
  "mime": "image/jpeg",
  "description": "login screen, big photo on the left, sign in with apple and google",
  "max_iterations": 2,
  "debug": false
}
```

Response is `application/x-ndjson`: one JSON object per line, as they happen.

| `type` | fields | meaning |
|--------|--------|---------|
| `status` | `message` | progress text, show it to the user |
| `draft` | `iteration`, `html`, `notes`, `tokens`, `seconds` | a new full HTML document. Render it immediately. |
| `render` | `iteration`, `png_base64` | screenshot of that draft. Only with `debug: true`. |
| `approved` | `iteration` | Gemma judged the render faithful to the sketch |
| `final` | `html`, `iterations`, `approved` | done. `html` is the one to keep. |
| `error` | `message` | something broke. Stream ends. |

The app should render each `draft` as it arrives so the user watches it refine, and keep
the `final` one.

`GET /healthz` process alive. `GET /readyz` returns 503 until Ollama has the model.

## Deploy

From your Mac, with the box up (`lambda/lambdactl.sh wait` done):

```bash
lambda/lambdactl.sh deploy
```

That rsyncs this folder to the box and runs `install.sh` there: venv, Chromium, systemd
unit `sketchboard`, and the nginx routes. Re-run after every change. Nothing here requires
relaunching the GPU box.

Try it end to end:

```bash
lambda/lambdactl.sh mockup server/samples/login.png "login screen with a photo on the left"
```

Logs on the box: `lambda/lambdactl.sh ssh sudo journalctl -u sketchboard -f`

## Local dev

```bash
cd server
uv venv && uv pip install -r requirements.txt
uv run pytest
OLLAMA_URL=http://<box-ip>:8080 RENDER_ENABLED=0 uv run uvicorn app.main:app --reload
```

Pointing `OLLAMA_URL` at the box's `/v1/` route won't work without the bearer token, so
for local runs either ssh-tunnel Ollama (`ssh -L 11434:127.0.0.1:11434 ubuntu@<ip>`) or
run Ollama locally with a small model (`ollama run gemma4:e4b`).

## Layout

```
app/main.py      FastAPI routes, request validation, NDJSON streaming
app/harness.py   the draft -> render -> critique loop
app/gemma.py     Ollama OpenAI-compatible client (images as data URLs)
app/render.py    Playwright screenshot at iPad viewport, network blocked
app/html.py      pull the HTML document out of a model reply
app/prompts.py   all prompt text. Tune here.
app/config.py    env-driven settings
install.sh       runs on the box; idempotent
sketchboard.service  systemd unit
samples/         test sketches (make_sketch.py generates one)
tests/           pytest
```

## Tuning knobs

- `MAX_ITERATIONS` (box `.env`, default 2): each pass is one Gemma call with two images,
  so roughly 20-40 s on an A100. 0 = single-shot.
- `prompts.py`: the system prompt fixes output format and iPad sizing. The critique prompt
  decides how picky the loop is.
- Viewport is 1180x820, iPad Pro 11" landscape. Change `VIEWPORT_W/H` if the app renders
  at a different size.
