"""Render HTML to a PNG with headless Chromium (Playwright).

One browser per process, launched lazily. If Playwright or Chromium isn't
available, `available()` is False and the harness skips the visual loop.
"""

import asyncio
from dataclasses import dataclass, field

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


@dataclass
class LayoutReport:
    """Cheap, deterministic facts about the rendered page. Fed to the critique
    prompt as text so the model doesn't have to eyeball them from a screenshot."""

    element_count: int = 0
    text_chars: int = 0
    scroll_height: int = 0
    scroll_width: int = 0
    overflow_x: list[str] = field(default_factory=list)   # elements poking past the right edge
    overflow_y: list[str] = field(default_factory=list)   # elements poking past the bottom edge
    tiny_text: list[str] = field(default_factory=list)    # font-size < 11px
    external_refs: list[str] = field(default_factory=list)  # src/href to http(s) that we blocked
    console_errors: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.overflow_x or self.overflow_y or self.tiny_text or self.external_refs
                    or self.console_errors or self.element_count < 5)

    def summary(self, width: int, height: int) -> str:
        """Bullet list for the prompt. Empty string when there's nothing to say."""
        lines: list[str] = []
        if self.element_count < 5:
            lines.append(f"page is nearly empty ({self.element_count} elements, {self.text_chars} chars of text)")
        if self.scroll_height > height + 8:
            lines.append(f"page scrolls vertically: content is {self.scroll_height}px tall in a {height}px viewport")
        if self.scroll_width > width + 8:
            lines.append(f"page scrolls horizontally: content is {self.scroll_width}px wide in a {width}px viewport")
        if self.overflow_x:
            lines.append("cut off at the right edge: " + ", ".join(self.overflow_x[:6]))
        if self.overflow_y:
            lines.append("cut off at the bottom edge: " + ", ".join(self.overflow_y[:6]))
        if self.tiny_text:
            lines.append("text smaller than 11px (illegible on iPad): " + ", ".join(self.tiny_text[:6]))
        if self.external_refs:
            lines.append("external resources (blocked, will not load on device): " + ", ".join(self.external_refs[:4]))
        if self.console_errors:
            lines.append("script errors: " + "; ".join(self.console_errors[:3]))
        return "\n".join(f"- {l}" for l in lines)


_LAYOUT_JS = """
(args) => {
  const [W, H] = args;
  const label = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    else if (el.className && typeof el.className === 'string') s += '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.');
    const t = (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 24);
    return t ? `${s} "${t}"` : s;
  };
  const all = Array.from(document.body.querySelectorAll('*'));
  const ox = [], oy = [], tiny = [];
  for (const el of all) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > W + 2 && r.left < W && ox.length < 12) ox.push(label(el));
    if (r.bottom > H + 2 && r.top < H && oy.length < 12) oy.push(label(el));
    const hasOwnText = Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim());
    if (hasOwnText && parseFloat(cs.fontSize) < 11 && tiny.length < 12) tiny.push(label(el));
  }
  const ext = Array.from(document.querySelectorAll('[src],[href],link[href]'))
    .map(el => el.getAttribute('src') || el.getAttribute('href') || '')
    .filter(u => /^https?:\\/\\//i.test(u)).slice(0, 8);
  return {
    element_count: all.length,
    text_chars: (document.body.innerText || '').trim().length,
    scroll_height: document.documentElement.scrollHeight,
    scroll_width: document.documentElement.scrollWidth,
    overflow_x: ox, overflow_y: oy, tiny_text: tiny, external_refs: ext,
  };
}
"""


async def render(html: str, *, width: int = config.VIEWPORT_W, height: int = config.VIEWPORT_H) -> tuple[bytes, LayoutReport]:
    """Render `html` at the iPad viewport. Returns (PNG bytes, layout report)."""
    browser = await _get_browser()
    page = await browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)[:160]))
    try:
        # Block network so a stray <script src> or <img src> can't stall the render.
        await page.route("**/*", lambda route: route.abort() if route.request.url.startswith("http") else route.continue_())
        await page.set_content(html, wait_until="domcontentloaded")
        await page.wait_for_timeout(150)  # let fonts/layout settle
        png = await page.screenshot(type="png", full_page=False)
        facts = await page.evaluate(_LAYOUT_JS, [width, height])
        report = LayoutReport(console_errors=errors, **facts)
        return png, report
    finally:
        await page.close()


async def screenshot(html: str, **kw) -> bytes:
    png, _ = await render(html, **kw)
    return png


async def shutdown() -> None:
    global _browser, _pw
    if _browser is not None:
        await _browser.close()
        _browser = None
    if _pw is not None:
        await _pw.stop()
        _pw = None
