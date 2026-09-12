import time

from app import sessions


def test_survives_cache_loss():
    sessions.start("s1", b"\x89PNG", "image/png", "login")
    sessions.update_html("s1", "<html>v1</html>")
    sessions._cache.clear()                       # simulate a restart
    s = sessions.get("s1")
    assert s is not None
    assert s.sketch == b"\x89PNG" and s.mime == "image/png" and s.description == "login"
    assert s.html == "<html>v1</html>"


def test_history_saved_on_demand():
    sessions.start("s2", b"x", "image/jpeg", "")
    s = sessions.get("s2")
    s.history.append("make it green")
    sessions.save("s2")
    sessions._cache.clear()
    assert sessions.get("s2").history == ["make it green"]


def test_expired_session_is_dropped():
    s = sessions.start("s3", b"x", "image/jpeg", "")
    s.touched = time.time() - sessions.SESSION_TTL_S - 1
    sessions._save(s)
    sessions._cache.clear()
    assert sessions.get("s3") is None


def test_unknown_session():
    assert sessions.get("nope") is None
