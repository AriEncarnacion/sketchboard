"""Draft -> render -> critique -> revise loop.

`run()` is an async generator of event dicts so the API can stream progress:

  {"type": "status",  "message": "..."}
  {"type": "draft_partial", "iteration": n, "html": "...", "chars": c}   the draft so far,
                                                     a few times a second while the model writes
  {"type": "draft",   "iteration": n, "html": "...", "notes": "...", "tokens": ..., "seconds": ...}
  {"type": "checks",  "iteration": n, "clean": bool, "problems": "- ...", "png_base64": "..." (debug only)}
  {"type": "verdict", "iteration": n, "problems": "- ...", "seconds": ...}   judge found problems
  {"type": "approved","iteration": n, "seconds": ...}                         judge approved
  {"type": "final",   "html": "...", "iterations": n, "approved": bool, "chosen": i, "score": s}
                                                     `chosen` is the draft iteration returned as html
  {"type": "error",   "message": "..."}
"""

import base64
import time
from collections.abc import AsyncIterator
from typing import Any

from . import config, prompts, render
from .gemma import Gemma, Reply, image_part, text_part
from .html import extract_html, is_approved, partial_html

# Streaming partials: at most this often, and only when the document grew by this much.
PARTIAL_MIN_INTERVAL_S = 0.25
PARTIAL_MIN_GROWTH = 48


def _system() -> dict[str, Any]:
    return {"role": "system", "content": prompts.SYSTEM.format(width=config.VIEWPORT_W, height=config.VIEWPORT_H)}


async def _ask_for_html(
    gemma: Gemma,
    messages: list[dict[str, Any]],
    model: str | None,
    *,
    iteration: int,
    stream: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    """Ask for an HTML document. Yields `draft_partial` events while the model writes,
    then exactly one {"type": "_result", "reply": Reply, "html": str | None} which the
    caller consumes and must not forward. If the reply has no HTML, asks once more for
    just the document (not streamed; it's the rare path)."""
    if stream and hasattr(gemma, "chat_stream"):
        reply, deltas = gemma.chat_stream(messages, model=model)
        last_emit, last_len = 0.0, 0
        async for _ in deltas:
            now = time.monotonic()
            if now - last_emit < PARTIAL_MIN_INTERVAL_S:
                continue
            part = partial_html(reply.text)
            if part is None or len(part) - last_len < PARTIAL_MIN_GROWTH:
                continue
            last_emit, last_len = now, len(part)
            yield {"type": "draft_partial", "iteration": iteration, "html": part, "chars": len(part)}
    else:
        reply = await gemma.chat(messages, model=model)

    html = extract_html(reply.text)
    if html is None and not is_approved(reply.text):
        retry = messages + [
            {"role": "assistant", "content": reply.text},
            {"role": "user", "content": prompts.REPAIR},
        ]
        reply = await gemma.chat(retry, model=model, temperature=0.2)
        html = extract_html(reply.text)
    yield {"type": "_result", "reply": reply, "html": html}


def _looks_like_problems(text: str) -> bool:
    """A judge reply we can act on: at least one bullet line."""
    return any(line.strip().startswith(("-", "*", "•")) for line in text.splitlines())


def _notes(text: str, html: str | None) -> str:
    """Whatever the model said before the code block, trimmed."""
    if html and html in text:
        return text.split(html, 1)[0].replace("```html", "").replace("```", "").strip()
    return text.strip()[:2000]


def _draft_event(iteration: int, reply: Reply, html: str) -> dict[str, Any]:
    return {
        "type": "draft", "iteration": iteration, "html": html, "notes": _notes(reply.text, html),
        "tokens": reply.prompt_tokens + reply.completion_tokens, "seconds": round(reply.seconds, 1),
    }


async def run(
    gemma: Gemma,
    sketch: bytes,
    mime: str,
    description: str,
    *,
    max_iterations: int | None = None,
    model: str | None = None,
    stream: bool = True,
    debug: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    iters = config.MAX_ITERATIONS if max_iterations is None else max(0, max_iterations)
    description = description.strip() or "(none)"
    sketch_img = image_part(sketch, mime)

    # --- draft ------------------------------------------------------------------
    yield {"type": "status", "message": f"drafting with {model or gemma.model}"}
    messages = [
        _system(),
        {"role": "user", "content": [text_part(prompts.DRAFT.format(description=description)), sketch_img]},
    ]
    reply: Reply
    html: str | None = None
    async for ev in _ask_for_html(gemma, messages, model, iteration=0, stream=stream):
        if ev["type"] == "_result":   # always the last event; let the generator finish
            reply, html = ev["reply"], ev["html"]
        else:
            yield ev
    if html is None:
        yield {"type": "error", "message": "model did not return HTML", "raw": reply.text[:2000]}
        return
    yield _draft_event(0, reply, html)

    if not render.available():
        if iters > 0:
            yield {"type": "status", "message": "renderer unavailable, skipping critique"}
        yield {"type": "final", "html": html, "iterations": 0, "approved": False, "chosen": 0}
        return

    # --- judge / revise -------------------------------------------------------------
    # Every draft is rendered, checked, and judged, including the last one. `iters` is the
    # number of revisions allowed. We keep the best-scoring draft, not the latest: an
    # unnecessary rewrite can make things worse.
    scored: list[tuple[int, int, str]] = []   # (score, iteration, html); lower is better
    approved_at: int | None = None
    n = 0
    for n in range(iters + 1):
        yield {"type": "status", "message": f"rendering draft {n}"}
        try:
            png, report = await render.render(html)
        except Exception as e:  # noqa: BLE001 - keep serving even if Chromium hiccups
            yield {"type": "status", "message": f"render failed ({e.__class__.__name__}), stopping"}
            scored.append((50, n, html))
            break
        checks_text = report.summary(config.VIEWPORT_W, config.VIEWPORT_H)
        yield {"type": "checks", "iteration": n, "clean": report.clean, "problems": checks_text,
               **({"png_base64": base64.b64encode(png).decode()} if debug else {})}

        # Judge: short verdict, no HTML. Cheap, and stops the model from rewriting a good page.
        yield {"type": "status", "message": f"judging draft {n}"}
        checks = (prompts.CHECKS_HEADER + checks_text + "\n") if checks_text else prompts.CHECKS_CLEAN
        judge = prompts.JUDGE.format(width=config.VIEWPORT_W, height=config.VIEWPORT_H,
                                     description=description, checks=checks)
        # Label the images inline: without labels the model occasionally claims the
        # second image is missing even though it was delivered.
        judge_msgs = [_system(), {"role": "user", "content": [
            text_part("Image 1, the hand-drawn sketch:"), sketch_img,
            text_part("Image 2, the rendered mockup screenshot:"), image_part(png, "image/png"),
            text_part(judge),
        ]}]
        verdict = await gemma.chat(judge_msgs, model=model, max_tokens=400, temperature=0.1)
        if not is_approved(verdict.text) and not _looks_like_problems(verdict.text):
            # Not a verdict (e.g. "please provide the screenshot"). One retry, then fall back.
            verdict = await gemma.chat(judge_msgs, model=model, max_tokens=400, temperature=0.3)
            if not is_approved(verdict.text) and not _looks_like_problems(verdict.text):
                yield {"type": "status", "message": "judge gave no verdict, using automated checks only"}
                verdict.text = ("APPROVED" if not checks_text
                                else "\n".join(f"- {l.lstrip('- ')}" for l in checks_text.splitlines()))
        if is_approved(verdict.text):
            approved_at = n
            scored.append((0, n, html))
            yield {"type": "approved", "iteration": n, "seconds": round(verdict.seconds, 1)}
            break
        problems = verdict.text.strip()
        if extract_html(problems):
            problems = _notes(problems, extract_html(problems)) or "see automated checks"
        n_problems = sum(1 for line in problems.splitlines() if line.strip().startswith(("-", "*", "•")))
        # Deterministic failures weigh more than the model's opinions.
        score = n_problems + 3 * len(checks_text.splitlines())
        scored.append((score, n, html))
        yield {"type": "verdict", "iteration": n, "problems": problems, "score": score,
               "seconds": round(verdict.seconds, 1)}
        if n == iters:
            break

        # Revise: fix exactly the listed problems.
        yield {"type": "status", "message": f"revising draft {n}"}
        revise = prompts.REVISE.format(html=html, problems=problems)
        messages = [_system(), {"role": "user", "content": [text_part(revise), sketch_img]}]
        new_html: str | None = None
        async for ev in _ask_for_html(gemma, messages, model, iteration=n + 1, stream=stream):
            if ev["type"] == "_result":
                reply, new_html = ev["reply"], ev["html"]
            else:
                yield ev
        if new_html is None:
            yield {"type": "status", "message": "revision returned no HTML, keeping previous draft"}
            break
        html = new_html
        yield _draft_event(n + 1, reply, html)

    # Best score wins; on a tie prefer the later draft (it had the fix applied).
    best_score, best_n, best_html = min(scored, key=lambda s: (s[0], -s[1]))
    yield {"type": "final", "html": best_html, "iterations": n, "approved": approved_at is not None,
           "chosen": best_n, "score": best_score}


async def edit(
    gemma: Gemma,
    sketch: bytes,
    mime: str,
    description: str,
    html: str,
    instruction: str,
    history: list[str],
    *,
    model: str | None = None,
    stream: bool = True,
    debug: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """Apply one follow-up instruction to an existing mockup. Single revise call plus a
    render + checks pass so the client gets the same event shapes as `run()`."""
    description = description.strip() or "(none)"
    hist = prompts.EDIT_HISTORY.format(items="\n".join(f"- {h}" for h in history)) if history else ""
    prompt = prompts.EDIT.format(html=html, description=description, history=hist, instruction=instruction.strip())

    yield {"type": "status", "message": f"editing with {model or gemma.model}"}
    messages = [_system(), {"role": "user", "content": [text_part(prompt), image_part(sketch, mime)]}]
    reply: Reply
    new_html: str | None = None
    async for ev in _ask_for_html(gemma, messages, model, iteration=0, stream=stream):
        if ev["type"] == "_result":
            reply, new_html = ev["reply"], ev["html"]
        else:
            yield ev
    if new_html is None:
        yield {"type": "error", "message": "model did not return HTML", "raw": reply.text[:2000]}
        return
    yield _draft_event(0, reply, new_html)

    score = 0
    if render.available():
        try:
            png, report = await render.render(new_html)
            checks_text = report.summary(config.VIEWPORT_W, config.VIEWPORT_H)
            score = 3 * len(checks_text.splitlines())
            yield {"type": "checks", "iteration": 0, "clean": report.clean, "problems": checks_text,
                   **({"png_base64": base64.b64encode(png).decode()} if debug else {})}
        except Exception as e:  # noqa: BLE001
            yield {"type": "status", "message": f"render failed ({e.__class__.__name__})"}

    yield {"type": "final", "html": new_html, "iterations": 0, "approved": False, "chosen": 0, "score": score}
