from app.html import extract_html, is_approved

DOC = "<!doctype html><html><body><h1>Hi</h1></body></html>"


def test_fenced_block():
    text = f"Here you go:\n```html\n{DOC}\n```\nDone."
    assert extract_html(text) == DOC


def test_fenced_block_without_language():
    text = f"```\n{DOC}\n```"
    assert extract_html(text) == DOC


def test_bare_document():
    text = f"Some notes.\n{DOC}\nMore notes."
    assert extract_html(text) == DOC


def test_fenced_block_with_trailing_prose_inside():
    text = f"```html\n{DOC}\nOops trailing\n```"
    assert extract_html(text) == DOC


def test_no_html():
    assert extract_html("just words") is None
    assert extract_html("") is None


def test_approved():
    assert is_approved("APPROVED")
    assert is_approved("  approved.\n")
    assert not is_approved("APPROVED but here is a fix:\n```html\n" + DOC + "\n```")
    assert not is_approved("Not approved")


def test_partial_html_before_document_starts():
    from app.html import partial_html
    assert partial_html("Here are the elements:\n- a\n- b\n") is None
    assert partial_html("- b\n``") is None
    assert partial_html("- b\n```html\n<!doctype") is None   # no complete tag yet


def test_partial_html_grows_and_trims_to_last_tag():
    from app.html import partial_html
    text = "notes\n```html\n<!doctype html><html><body><div cla"
    assert partial_html(text) == "<!doctype html><html><body>"
    text += 'ss="x">hi</div><p>partial te'
    assert partial_html(text) == '<!doctype html><html><body><div class="x">hi</div><p>'


def test_partial_html_stops_at_closing_fence():
    from app.html import partial_html
    assert partial_html("```html\n<html><p>x</p></html>\n```\nThat's it, <b>done</b>.") == "<html><p>x</p></html>"
    assert partial_html("```html\n<html><p>x</p></html>\n``") == "<html><p>x</p></html>"


def test_partial_html_bare_document():
    from app.html import partial_html
    assert partial_html("Sure.\n<!DOCTYPE html>\n<html><head><title>t</title>") == "<!DOCTYPE html>\n<html><head><title>t</title>"
