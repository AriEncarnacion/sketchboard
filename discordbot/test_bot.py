"""Unit tests for the pure helpers. No Discord, no harness."""

from types import SimpleNamespace

import bot


def test_session_id():
    assert bot.session_id(1290000000000000001) == "discord-1290000000000000001"
    assert len(bot.session_id(2**63)) <= 64


def test_strip_mentions():
    assert bot.strip_mentions("<@123> make it green <@!456>") == "make it green"
    assert bot.strip_mentions("") == ""


def test_is_image():
    assert bot.is_image(SimpleNamespace(content_type="image/png"))
    assert bot.is_image(SimpleNamespace(content_type="image/jpeg; charset=binary"))
    assert not bot.is_image(SimpleNamespace(content_type="image/heic"))
    assert not bot.is_image(SimpleNamespace(content_type=None))


def test_thread_name():
    assert bot.thread_name("") == "Mockup"
    assert bot.thread_name("login screen\nmore") == "login screen"
    long = bot.thread_name("x" * 100)
    assert len(long) == 61 and long.endswith("…")


def test_quote_truncates():
    q = bot.quote("a\nb\n" + "x" * 1000, limit=20)
    assert q.startswith("> a\n> b") and q.endswith("…")
