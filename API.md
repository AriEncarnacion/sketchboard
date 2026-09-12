# Sketchboard client ↔ server contract (v1)

The iPad app talks to the harness on the Lambda box. This file is the agreement between
`Sketchboard/Backend/` (Swift) and `server/app/main.py` (Python). Change both when you
change this.

## Transport

- Base URL: `http://<box-ip>:8080` (plain HTTP for the hackathon; new IP every launch).
- Every `/api/` request carries `Authorization: Bearer <GEMMA_TOKEN>`. Missing or wrong → `401` from nginx.
- Request bodies are JSON. Streaming responses are `application/x-ndjson`: one JSON object per line, flushed as it happens. The client should read line by line, not wait for the body to end.
- `GET /readyz` → `200` when the model is loaded, `503` otherwise. No auth. Use it for the app's "backend online" indicator.

## `POST /api/v1/mockup`

Turn a sketch into a mockup.

```json
{
  "image_base64": "<jpeg/png, base64, no data: prefix>",
  "mime": "image/jpeg",
  "description": "login screen, photo on the left, sign in with apple and google",
  "session_id": "ipad-8F3A",
  "max_iterations": 2,
  "model": "gemma4:26b",
  "debug": false
}
```

| field | required | notes |
|---|---|---|
| `image_base64` | yes | ≤ 20 MB decoded. JPEG at ~1180×820 is plenty. |
| `mime` | no | `image/jpeg` (default), `image/png`, `image/webp` |
| `description` | no | dictated notes, ≤ 4000 chars |
| `session_id` | no | `[A-Za-z0-9._-]{1,64}`, client-chosen. Omit and the server mints one. Needed for `/edit`. |
| `max_iterations` | no | 0–5 revisions. Server default 2. |
| `model` | no | Ollama tag override, e.g. `gemma4:31b` |
| `stream` | no | default `true`: emit `draft_partial` events while the model writes |
| `debug` | no | adds `png_base64` to `checks` events |

## `POST /api/v1/edit`

Apply a follow-up instruction to the session's current mockup.

```json
{ "session_id": "ipad-8F3A", "instruction": "make the login button dark green" }
```

`404` if the session is unknown or has no mockup yet. Sessions live in server memory for
6 hours of inactivity; a server restart clears them. Same stream shape as `/mockup`.

## `GET /api/v1/session/{id}`

`{ "session_id", "description", "html", "history": ["edit 1", "edit 2"] }`. For reconnects
and debugging.

## Event stream

Every line has a `type`. Unknown types must be ignored, and unknown fields on known types
must be ignored, so the server can add things without breaking older app builds.

| `type` | fields | client action |
|---|---|---|
| `session` | `session_id` | always first. Remember it for `/edit`. |
| `status` | `message` | show as progress text |
| `draft_partial` | `iteration`, `html`, `chars` | the draft so far, a few times a second while the model writes. `html` is the whole partial document (not a delta), already cut at the last complete tag. Render it in place; expect it to grow. Off with `"stream": false`. |
| `draft` | `iteration`, `html`, `notes`, `tokens`, `seconds` | render `html` now. Replace the previous draft (and any partial). |
| `checks` | `iteration`, `clean`, `problems`, `png_base64`? | optional: show `problems` while the judge runs |
| `verdict` | `iteration`, `problems`, `score`, `seconds` | optional: show what the judge wants fixed |
| `approved` | `iteration`, `seconds` | optional: a "looks good" affordance |
| `final` | `html`, `chosen`, `score`, `approved`, `iterations` | always last on success. Render `html`; it may be an earlier draft than the last one shown. |
| `error` | `message`, `raw`? | always last on failure. Show `message`. |

Timing on the A100 with the default model: first `draft` after ~25 s, `final` after ~30 s
when the first draft is approved, ~60 s with two revisions. Keep the HTTP read timeout
≥ 10 minutes; events arrive at least every ~70 s.

## HTML the server sends

One self-contained document: inline `<style>`, system fonts, no external scripts, fonts,
or images, sized for 1180×820 CSS px (iPad Pro 11" landscape). Render it in a `WKWebView`
with `loadHTMLString(_:baseURL: nil)`. Nothing in it needs the network.

## Versioning

Breaking changes bump the path (`/api/v2/`). `GET /healthz` reports `api_version`.
`/api/mockup` (unversioned) is a temporary alias for `/api/v1/mockup`.
