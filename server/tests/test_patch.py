from app.patch import Hunk, apply, parse

DOC = """<!doctype html>
<html>
<head>
<style>
  .btn { background: #007aff; }
</style>
</head>
<body>
  <div class="form">
    <button class="btn">Log in</button>
  </div>
</body>
</html>"""


def test_parse_blocks():
    text = ("Sure.\n<<<<<<< SEARCH\n  a\n  b\n=======\n  c\n>>>>>>> REPLACE\n\n"
            "<<<<<<< SEARCH\nx\n=======\n\n>>>>>>> REPLACE\n")
    hunks = parse(text)
    assert hunks == [Hunk("  a\n  b", "  c"), Hunk("x", "")]
    assert parse("no blocks here") == []


def test_apply_exact():
    out, note = apply(DOC, [Hunk("  .btn { background: #007aff; }", "  .btn { background: #34c759; }")])
    assert out and "#34c759" in out and "#007aff" not in out
    assert "1 hunk" in note


def test_apply_loose_whitespace_and_reindent():
    # Model dropped the indentation in SEARCH and used different indentation in REPLACE.
    hunk = Hunk('<button class="btn">Log in</button>',
                '<label><input type="checkbox"> Remember me</label>\n<button class="btn">Log in</button>')
    out, _ = apply(DOC, [hunk])
    assert out is not None
    assert '    <label><input type="checkbox"> Remember me</label>\n    <button class="btn">Log in</button>' in out


def test_apply_multiple_in_order():
    hunks = [
        Hunk("  .btn { background: #007aff; }", "  .btn { background: #34c759; }\n  .note { font-size: 12px; }"),
        Hunk('    <button class="btn">Log in</button>', '    <button class="btn">Log in</button>\n    <p class="note">Forgot?</p>'),
    ]
    out, note = apply(DOC, hunks)
    assert out and ".note" in out and 'class="note"' in out and "2 hunk" in note


def test_apply_fails_atomically():
    hunks = [Hunk("  .btn { background: #007aff; }", "  .btn { background: red; }"), Hunk("<nope>", "<x>")]
    out, note = apply(DOC, hunks)
    assert out is None and "hunk 2" in note


def test_apply_rejects_noop_and_empty():
    assert apply(DOC, [])[0] is None
    assert apply(DOC, [Hunk("   ", "x")])[0] is None
    assert apply(DOC, [Hunk("<html>", "<html>")])[0] is None


def test_apply_fuzzy_near_miss():
    # Model dropped the trailing semicolon and changed the hex case.
    hunk = Hunk(".btn { background: #007AFF }", ".btn { background: #34c759; border-radius: 4px; }")
    out, note = apply(DOC, [hunk])
    assert out is not None and "#34c759; border-radius: 4px" in out and "#007aff" not in out


def test_apply_fuzzy_rejects_far_miss():
    hunk = Hunk(".btn { color: white; padding: 20px 40px; font-weight: bold }", "x")
    out, note = apply(DOC, [hunk])
    assert out is None and "not found" in note and ".btn" in note
