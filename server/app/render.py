"""Render HTML to a PNG with headless Chromium (Playwright).

One browser per process, launched lazily. If Playwright or Chromium isn't
available, `available()` is False and the harness skips the visual loop.
"""

import asyncio

from . import config

try:
    from playwright.async_api import Browser, async_playwright
except ImportError:  # playwright not installed
    async_playwright = None  # type: ignore[assignment]
    Browser = None  # type: ignore[assignment,misc]

_browser: "Browser | None" = None
_pw = None
_lock = asyncio.Lock()


def available() -> bool:
    return config.RENDER_ENABLED and async_playwright is not None


async def _get_browser() -> "Browser":
    global _browser, _pw
    async with _lock:
        if _browser is None or not _browser.is_connected():
            _pw = await async_playwright().start()
            _browser = await _pw.chromium.launch(args=["--no-sandbox"])
    return _browser


async def screenshot(html: str, *, width: int = config.VIEWPORT_W, height: int = config.VIEWPORT_H) -> bytes:
    """Render `html` at the iPad viewport and return PNG bytes."""
    browser = await _get_browser()
    page = await browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
    try:
        # Block network so a stray <script src> or <img src> can't stall the render.
        await page.route("**/*", lambda route: route.abort() if route.request.url.startswith("http") else route.continue_())
        await page.set_content(html, wait_until="domcontentloaded")
        await page.wait_for_timeout(150)  # let fonts/layout settle
        return await page.screenshot(type="png", full_page=False)
    finally:
        await page.close()


async def shutdown() -> None:
    global _browser, _pw
    if _browser is not None:
        await _browser.close()
        _browser = None
    if _pw is not None:
        await _pw.stop()
        _pw = None
