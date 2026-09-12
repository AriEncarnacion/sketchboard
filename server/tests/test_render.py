"""Exercises the real Chromium render. Skipped when Playwright's Chromium isn't installed."""

import asyncio

import pytest

from app import render

pytestmark = pytest.mark.skipif(not render.available(), reason="playwright not installed")

W, H = render.config.VIEWPORT_W, render.config.VIEWPORT_H


@pytest.fixture(scope="module")
def loop():
    """One loop for the whole module: the browser and its lock are bound to it."""
    lp = asyncio.new_event_loop()
    try:
        lp.run_until_complete(asyncio.wait_for(render.render("<html><body><p>probe</p></body></html>"), 60))
    except Exception as e:  # noqa: BLE001
        lp.close()
        pytest.skip(f"chromium not available: {e}")
    yield lp
    lp.run_until_complete(render.shutdown())
    lp.close()


def test_clean_page(loop):
    html = """<!doctype html><html><body style="margin:0">
      <header style="height:60px">Title</header>
      <main style="display:flex;gap:16px;padding:16px">
        <section style="flex:1;height:400px;background:#eee">Left</section>
        <section style="flex:1;height:400px;background:#ddd">Right</section>
      </main><footer>ok</footer></body></html>"""
    png, rep = loop.run_until_complete(render.render(html))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert rep.clean, rep.summary(W, H)


def test_overflow_and_tiny_text_and_external(loop):
    html = """<!doctype html><html><head><link rel="stylesheet" href="https://example.com/x.css"></head>
      <body style="margin:0">
      <div id="wide" style="width:3000px;height:20px;background:red">wide</div>
      <div id="tall" style="position:absolute;top:800px;height:200px;background:blue">tall</div>
      <p style="font-size:8px">fine print</p>
      </body></html>"""
    _, rep = loop.run_until_complete(render.render(html))
    assert not rep.clean
    s = rep.summary(W, H)
    assert "div#wide" in s and "right edge" in s
    assert "div#tall" in s and "bottom edge" in s
    assert "fine print" in s and "11px" in s
    assert "example.com" in s
    assert "scrolls" in s


def test_script_error_captured(loop):
    html = "<html><body><p>x</p><p>y</p><p>z</p><p>w</p><p>v</p><script>throw new Error('boom')</script></body></html>"
    _, rep = loop.run_until_complete(render.render(html))
    assert any("boom" in e for e in rep.console_errors)


def test_base_css_split_lays_out_side_by_side(loop):
    """Regression: the model tends to write <div class="screen split">; that must be a row."""
    from app import basecss
    for cls in ("screen split", "screen light split", "screen"):
        inner = '<div id="a" class="fill">a</div><div id="b" class="fill">b</div>'
        html = basecss.inject(f'<div class="{cls}">' + (inner if "split" in cls else f'<div class="split">{inner}</div>') + "</div>")
        _, rep = loop.run_until_complete(render.render(html))
        assert not rep.overflow_x and not rep.overflow_y and rep.scroll_height <= H, rep.summary(W, H)
        boxes = loop.run_until_complete(_boxes(html, ["#a", "#b"]))
        a, b = boxes["#a"], boxes["#b"]
        assert abs(a["y"] - b["y"]) < 2 and b["x"] > a["x"] + 400, (cls, boxes)
        assert a["width"] > 500 and a["height"] > 700, (cls, boxes)


async def _boxes(html, selectors):
    browser = await render._get_browser()
    page = await browser.new_page(viewport={"width": W, "height": H})
    try:
        await page.set_content(html)
        return {s: await page.eval_on_selector(s, "e => { const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: r.height}; }") for s in selectors}
    finally:
        await page.close()


def test_warm_starts_browser_and_renders(loop):
    assert loop.run_until_complete(render.warm()) is True
    assert render._browser is not None and render._browser.is_connected()


def test_warm_is_noop_when_unavailable(loop, monkeypatch):
    monkeypatch.setattr(render, "available", lambda: False)
    assert loop.run_until_complete(render.warm()) is False
