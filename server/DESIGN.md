# Harness design

How a sketch becomes a mockup, and why the loop is shaped the way it is. Numbers are from
a Lambda `gpu_1x_a100_sxm4` (40 GB) running Ollama, measured 2026-09-12.

## The loop

```
sketch + notes
     │
     ▼
  DRAFT  ──────────────► html₀
     │
     ▼  for each draft i (up to MAX_ITERATIONS revisions):
  RENDER   headless Chromium at 1180x820 ─► screenshot + layout facts
  CHECKS   deterministic: overflow, scroll, tiny text, external refs, JS errors
  JUDGE    Gemma sees sketch + screenshot + checks ─► "APPROVED" or ≤5 problems (no HTML)
     │  approved ─► done
     ▼
  REVISE   Gemma gets html_i + problem list ─► html_{i+1}
     │
     ▼
  FINAL    the best-scored draft (not necessarily the latest)
```

Every event streams to the client as NDJSON as it happens. The app renders each `draft`
immediately so the user watches the mockup refine.

## Decisions

**Server-side, not app-side.** One request from the iPad, the loop runs next to the GPU.
The judge can use a real browser, prompts change without an app build, and there's one
place to log and debug. The app only needs to render HTML and show progress.

**Gemma emits a self-contained HTML document; the app renders it in a `WKWebView`.**
Most free-form output format, and the one Gemma is strongest at. A JSON schema mapped to
SwiftUI components would feel more native but constrains what can be drawn. The harness
contract is format-agnostic, so this can change later without touching the loop.

**Thinking is off.** Gemma 4 reasons by default and spends the whole token budget doing it:
a 600-token call returned empty content and 1.8k characters of reasoning. We send
`reasoning_effort: "none"` on every call (Ollama's OpenAI endpoint ignores `think:false`).
`REASONING=low` is available for experiments; it needs a much larger `MAX_TOKENS`.

**Judge and revise are separate calls.** A single "critique and fix" call always rewrote
the whole page, even when the draft was fine, and the rewrites drifted (a placeholder X
leaked into the render; elements moved). Split, the judge is a ~100-token call that costs
about a second, and the revise call only runs when there is a concrete list to fix.

**Deterministic checks before the model's opinion.** Chromium reports what overflows the
viewport, what scrolls, what's illegibly small, and what points at the network. These are
facts, fed into the judge prompt as text, and weighted 3x a model-reported problem in the
score. Cheaper and more reliable than asking the model to eyeball two images for them.

**Every draft is judged, including the last, and the best one wins.** Score = model
problems + 3 × deterministic problems; approved = 0. Ties go to the later draft. This
stops a bad final revision from replacing a good earlier one.

## Model choice

| model | params | speed | draft of the login sketch | first-draft quality |
|---|---|---|---|---|
| `gemma4:31b` | 30.7B dense | 42 tok/s | 64 s | faithful; generic placeholder icons |
| `gemma4:26b` | 25.2B MoE, 3.8B active | ~160 tok/s | 22-26 s | faithful; brand-style icons, tighter spacing |

Both are vision models. The MoE is about 3x faster on a real draft and its output was at
least as good. Default is `gemma4:26b`; `31b` stays pulled on the box and can be
requested per call with `"model": "gemma4:31b"`.

### Runs on the sample login sketch

| harness | model | wall time | what happened |
|---|---|---|---|
| v1 (critique+fix in one call) | 26b | 62 s | 3 drafts, never approved, draft 2 was worse than draft 0 |
| v1 | 31b | 180 s | 3 drafts, never approved |
| v2 (judge, then revise) | 26b | 29 s | draft 0 approved by the judge in 1.4 s |

v2 hasn't yet been exercised on a draft with real problems. That needs the eval set below.

## Latency budget

For a demo, the first draft should appear in under 30 s and the loop should finish
within about 60 s. Levers, in the order to pull them:

1. `MAX_ITERATIONS=1`. One judge pass catches the gross errors; the second rarely helps.
2. **Streaming. Done.** The draft call streams; `draft_partial` events carry the document
   so far, cut at the last complete tag, at most 4/s and only when it grew. On the login
   sketch the first partial lands ~1 s into a 14 s draft. Caveat: partials stall while the
   model writes the `<style>` block (nothing in CSS closes a tag), then jump. Which is why:
3. Base stylesheet. Inject a fixed CSS reset + component classes from the server and let
   Gemma emit body markup only. Cuts output tokens roughly in half and makes streaming
   look styled from the first element. Not done yet.

## Open questions for the team

- **Follow-up edits.** "Make the button blue" needs the server to keep the last HTML per
  session. An in-memory dict keyed by a client-generated session id is enough for the
  hackathon. Changes the API (add `session_id`, add `POST /api/edit`).
- **Eval set.** Five to ten real Pencil sketches with a one-line note each, checked into
  `server/samples/`. Every prompt change gets run against all of them. Without this,
  prompt tuning is guesswork.
- **HTML vs native.** See above. Decide before the app's render path is built.

## Things that bit us

- Ollama's CLI panics without `$HOME`; cloud-init has none. Use the HTTP API to pull.
- Ollama returns 403 when the `Host` header isn't localhost. nginx must set it explicitly.
- Gemma's reasoning eats `max_tokens`. Always send `reasoning_effort`.
