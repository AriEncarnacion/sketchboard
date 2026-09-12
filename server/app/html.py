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


def is_approved(text: str) -> bool:
    """The critique step replies with exactly APPROVED when the render matches."""
    head = text.strip()[:40].upper()
    return head.startswith(APPROVED) and extract_html(text) is None
