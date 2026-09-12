"""Draft -> render -> critique -> revise loop.

`run()` is an async generator of event dicts so the API can stream progress:

  {"type": "status",  "message": "..."}
  {"type": "draft",   "iteration": n, "html": "...", "notes": "...", "tokens": ..., "seconds": ...}
  {"type": "checks",  "iteration": n, "clean": bool, "problems": "- ...", "png_base64": "..." (debug only)}
  {"type": "verdict", "iteration": n, "problems": "- ...", "seconds": ...}   judge found problems
  {"type": "approved","iteration": n, "seconds": ...}                         judge approved
  {"type": "final",   "html": "...", "iterations": n, "approved": bool, "chosen": i, "score": s}
                                                     `chosen` is the draft iteration returned as html
  {"type": "error",   "message": "..."}
"""

import base64
from collections.abc import AsyncIterator
from typing import Any

from . import config, prompts, render
from .gemma import Gemma, Reply, image_part, text_part
from .html import extract_html, is_approved


def _system() -> dict[str, Any]:
    return {"role": "system", "content": prompts.SYSTEM.format(width=config.VIEWPORT_W, height=config.VIEWPORT_H)}


async def _ask_for_html(gemma: Gemma, messages: list[dict[str, Any]], model: str | None) -> tuple[Reply, str | None]:
    """Chat once; if the reply has no HTML, ask once more for just the document."""
    reply = await gemma.chat(messages, model=model)
    html = extract_html(reply.text)
    if html is None and not is_approved(reply.text):
        messages = messages + [
            {"role": "assistant", "content": reply.text},
            {"role": "user", "content": prompts.REPAIR},
        ]
        reply = await gemma.chat(messages, model=model, temperature=0.2)
        html = extract_html(reply.text)
    return reply, html


def _notes(text: str, html: str | None) -> str:
    """Whatever the model said before the code block, trimmed."""
    if html and html in text:
        return text.split(html, 1)[0].replace("```html", "").replace("```", "").strip()
    return text.strip()[:2000]


async def run(
    gemma: Gemma,
    sketch: bytes,
    mime: str,
    description: str,
    *,
    max_iterations: int | None = None,
    model: str | None = None,
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
    reply, html = await _ask_for_html(gemma, messages, model)
    if html is None:
        yield {"type": "error", "message": "model did not return HTML", "raw": reply.text[:2000]}
        return
    yield {
        "type": "draft", "iteration": 0, "html": html, "notes": _notes(reply.text, html),
        "tokens": reply.prompt_tokens + reply.completion_tokens, "seconds": round(reply.seconds, 1),
    }

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
        verdict = await gemma.chat(
            [_system(), {"role": "user", "content": [text_part(judge), sketch_img, image_part(png, "image/png")]}],
            model=model, max_tokens=400, temperature=0.1,
        )
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
        reply, new_html = await _ask_for_html(gemma, messages, model)
        if new_html is None:
            yield {"type": "status", "message": "revision returned no HTML, keeping previous draft"}
            break
        html = new_html
        yield {
            "type": "draft", "iteration": n + 1, "html": html, "notes": _notes(reply.text, html),
            "tokens": reply.prompt_tokens + reply.completion_tokens, "seconds": round(reply.seconds, 1),
        }

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
    debug: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """Apply one follow-up instruction to an existing mockup. Single revise call plus a
    render + checks pass so the client gets the same event shapes as `run()`."""
    description = description.strip() or "(none)"
    hist = prompts.EDIT_HISTORY.format(items="\n".join(f"- {h}" for h in history)) if history else ""
    prompt = prompts.EDIT.format(html=html, description=description, history=hist, instruction=instruction.strip())

    yield {"type": "status", "message": f"editing with {model or gemma.model}"}
    messages = [_system(), {"role": "user", "content": [text_part(prompt), image_part(sketch, mime)]}]
    reply, new_html = await _ask_for_html(gemma, messages, model)
    if new_html is None:
        yield {"type": "error", "message": "model did not return HTML", "raw": reply.text[:2000]}
        return
    yield {
        "type": "draft", "iteration": 0, "html": new_html, "notes": _notes(reply.text, new_html),
        "tokens": reply.prompt_tokens + reply.completion_tokens, "seconds": round(reply.seconds, 1),
    }

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
