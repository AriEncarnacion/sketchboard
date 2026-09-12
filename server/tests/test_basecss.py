from app import basecss
from app.html import extract_html

FRAG = '<style>.x{color:red}</style>\n<div class="screen"><div class="row"><button class="btn btn-primary">Go</button></div></div>'


def test_fragment_becomes_full_document_with_base_css():
    full = basecss.inject(FRAG)
    assert full.startswith("<!doctype html>") and full.endswith("</html>")
    assert f'<style id="{basecss.STYLE_ID}">' in full and ".btn-primary{" in full
    assert FRAG in full
    # The page's own <style> comes after the base block, so it wins on ties.
    assert full.index(basecss.STYLE_ID) < full.index(".x{color:red}")


def test_strip_and_inject_round_trip():
    full = basecss.inject(FRAG)
    shown = basecss.strip(full)
    assert basecss.PLACEHOLDER in shown and ".btn-primary{" not in shown
    assert len(shown) < len(full) // 2
    assert basecss.inject(shown) == full
    assert basecss.strip(basecss.inject(shown)) == shown


def test_full_document_without_base_gets_it_injected():
    doc = "<!doctype html><html><head><title>t</title></head><body><p>x</p></body></html>"
    full = basecss.inject(doc)
    assert full.count(basecss.STYLE_ID) == 1 and full.index(basecss.STYLE_ID) < full.index("<title>")
    assert basecss.inject(full) == full   # idempotent


def test_document_without_head_gets_one():
    full = basecss.inject("<html><body><p>x</p></body></html>")
    assert "<head>" in full and basecss.STYLE_ID in full


def test_guide_only_names_classes_that_exist():
    import re
    names = set(re.findall(r"\.([a-z][a-z0-9-]*)", basecss.GUIDE))
    css_names = set(re.findall(r"\.([a-z][a-z0-9-]*)", basecss.BASE_CSS))
    missing = sorted(n for n in names if n not in css_names and not n.startswith("icon-NAME"))
    assert not missing, f"in GUIDE but not in BASE_CSS: {missing}"
    icons = re.search(r"NAME is one of: (.*)", basecss.GUIDE).group(1).split()
    assert all(f".icon-{i}{{" in basecss.BASE_CSS for i in icons)


def test_extract_html_accepts_unfenced_fragment():
    text = "Elements: header, form.\n\n" + FRAG + "\n\nDone."
    assert extract_html(text) == FRAG
    assert extract_html("```html\n" + FRAG + "\n```") == FRAG
