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
