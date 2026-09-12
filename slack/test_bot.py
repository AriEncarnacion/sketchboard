"""Unit tests for the pure helpers. No Slack, no harness."""

import bot


def test_session_id_is_deterministic_and_url_safe():
    a = bot.session_id("C0123ABC", "1726160000.123456")
    assert a == "slack-C0123ABC-1726160000-123456"
    assert a == bot.session_id("C0123ABC", "1726160000.123456")
    assert "." not in a and len(a) <= 64


def test_strip_mentions():
    assert bot.strip_mentions("<@U123> make it green <@U456>") == "make it green"
    assert bot.strip_mentions(None) == ""


def test_is_image():
    assert bot.is_image({"mimetype": "image/png"})
    assert bot.is_image({"mimetype": "IMAGE/JPEG"})
    assert not bot.is_image({"mimetype": "image/heic"})
    assert not bot.is_image({"mimetype": "application/pdf"})
    assert not bot.is_image({})


def test_quote_truncates():
    q = bot.quote("a\nb\n" + "x" * 1000, limit=20)
    assert q.startswith("> a\n> b")
    assert q.endswith("…")
