"""Pull a usable HTML document out of a model reply."""

import re

_FENCE = re.compile(r"```(?:html|HTML)?\s*\n(.*?)```", re.DOTALL)
_DOC = re.compile(r"(<!doctype html.*?</html\s*>|<html.*?</html\s*>)", re.DOTALL | re.IGNORECASE)

APPROVED = "APPROVED"


def extract_html(text: str) -> str | None:
    """Return the HTML document in `text`, or None if there isn't one.

    Prefers a fenced ```html block, then a bare <html>...</html> document.
    A fenced block that itself contains a full document is trimmed to it.
    """
    if not text:
        return None
    for m in _FENCE.finditer(text):
        block = m.group(1).strip()
        doc = _DOC.search(block)
        if doc:
            return doc.group(1).strip()
        if "<" in block and ">" in block:
            return block
    doc = _DOC.search(text)
    if doc:
        return doc.group(1).strip()
    return None


_PARTIAL_START = re.compile(r"```(?:html|HTML)?[ \t]*\n|<!doctype html|<html[\s>]", re.IGNORECASE)


def partial_html(text: str) -> str | None:
    """The HTML document so far, from a reply that is still streaming.

    Starts at the opening ```html fence (or a bare <!doctype>/<html>), stops before any
    closing fence, and trims back to the last complete tag so a half-written `<div cla`
    never reaches the browser. None until the document has started.
    """
    m = _PARTIAL_START.search(text)
    if not m:
        return None
    start = m.end() if m.group(0).startswith("```") else m.start()
    body = text[start:]
    end = body.find("```")
    if end != -1:
        body = body[:end]
    else:
        body = body.rstrip("`")  # a fence arriving one backtick at a time
    cut = body.rfind(">")
    if cut == -1:
        return None
    return body[: cut + 1].strip() or None


def is_approved(text: str) -> bool:
    """The critique step replies with exactly APPROVED when the render matches."""
    head = text.strip()[:40].upper()
    return head.startswith(APPROVED) and extract_html(text) is None
