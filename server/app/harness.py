"""Draft -> render -> critique -> revise loop.

`run()` is an async generator of event dicts so the API can stream progress:

  {"type": "status",  "message": "..."}
  {"type": "draft",   "iteration": n, "html": "...", "notes": "...", "tokens": ..., "seconds": ...}
  {"type": "render",  "iteration": n, "png_base64": "..."}            (only when debug=True)
  {"type": "approved","iteration": n}
  {"type": "final",   "html": "...", "iterations": n, "approved": bool}
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


async def _ask_for_html(gemma: Gemma, messages: list[dict[str, Any]]) -> tuple[Reply, str | None]:
    """Chat once; if the reply has no HTML, ask once more for just the document."""
    reply = await gemma.chat(messages)
    html = extract_html(reply.text)
    if html is None and not is_approved(reply.text):
        messages = messages + [
            {"role": "assistant", "content": reply.text},
            {"role": "user", "content": prompts.REPAIR},
        ]
        reply = await gemma.chat(messages, temperature=0.2)
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
    debug: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    iters = config.MAX_ITERATIONS if max_iterations is None else max(0, max_iterations)
    description = description.strip() or "(none)"
    sketch_img = image_part(sketch, mime)

    # --- draft ------------------------------------------------------------------
    yield {"type": "status", "message": "drafting"}
    messages = [
        _system(),
        {"role": "user", "content": [text_part(prompts.DRAFT.format(description=description)), sketch_img]},
    ]
    reply, html = await _ask_for_html(gemma, messages)
    if html is None:
        yield {"type": "error", "message": "model did not return HTML", "raw": reply.text[:2000]}
        return
    yield {
        "type": "draft", "iteration": 0, "html": html, "notes": _notes(reply.text, html),
        "tokens": reply.prompt_tokens + reply.completion_tokens, "seconds": round(reply.seconds, 1),
    }

    approved = False
    n = 0
    if not render.available():
        if iters > 0:
            yield {"type": "status", "message": "renderer unavailable, skipping critique"}
        yield {"type": "final", "html": html, "iterations": 0, "approved": False}
        return

    # --- critique / revise --------------------------------------------------------
    for n in range(1, iters + 1):
        yield {"type": "status", "message": f"rendering draft {n - 1}"}
        try:
            png = await render.screenshot(html)
        except Exception as e:  # noqa: BLE001 - keep serving even if Chromium hiccups
            yield {"type": "status", "message": f"render failed ({e.__class__.__name__}), stopping"}
            break
        if debug:
            yield {"type": "render", "iteration": n - 1, "png_base64": base64.b64encode(png).decode()}

        yield {"type": "status", "message": f"critiquing draft {n - 1}"}
        critique = prompts.CRITIQUE.format(width=config.VIEWPORT_W, height=config.VIEWPORT_H, description=description)
        messages = [
            _system(),
            {"role": "user", "content": [text_part(critique), sketch_img, image_part(png, "image/png")]},
        ]
        reply, new_html = await _ask_for_html(gemma, messages)
        if is_approved(reply.text):
            approved = True
            yield {"type": "approved", "iteration": n - 1}
            break
        if new_html is None:
            yield {"type": "status", "message": "critique returned no HTML, keeping previous draft"}
            break
        html = new_html
        yield {
            "type": "draft", "iteration": n, "html": html, "notes": _notes(reply.text, html),
            "tokens": reply.prompt_tokens + reply.completion_tokens, "seconds": round(reply.seconds, 1),
        }

    yield {"type": "final", "html": html, "iterations": n if not approved else n - 1, "approved": approved}
