"""Screen formats. The designer's notes pick one; the app can override per request.
Compose, render, and judge all use the same width x height."""

import re

# name -> (width, height, how the system prompt describes it)
FORMATS: dict[str, tuple[int, int, str]] = {
    "phone": (390, 844, "an iPhone in portrait"),
    "tablet": (1180, 820, "an iPad in landscape"),
    "desktop": (1440, 900, "a desktop web browser window"),
}
DEFAULT = "tablet"

_PHONE = re.compile(r"\b(phone|mobile|iphone|android|ios app|portrait)\b", re.I)
_DESKTOP = re.compile(r"\b(desktop|web ?app|web ?site|web ?page|browser|dashboard|landing page|saas)\b", re.I)
_TABLET = re.compile(r"\b(ipad|tablet)\b", re.I)


def detect(description: str) -> str:
    """Keyword scan of the dictated notes. Explicit device words win; default is tablet."""
    # ponytail: keywords, not a model call. Add words here when a demo phrase misses.
    if _TABLET.search(description):
        return "tablet"
    if _PHONE.search(description):
        return "phone"
    if _DESKTOP.search(description):
        return "desktop"
    return DEFAULT


def size(name: str) -> tuple[int, int]:
    w, h, _ = FORMATS.get(name, FORMATS[DEFAULT])
    return w, h
