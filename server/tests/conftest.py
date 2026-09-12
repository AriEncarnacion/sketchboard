import pytest

from app import config, sessions


@pytest.fixture(autouse=True)
def _sessions_in_tmp(tmp_path, monkeypatch):
    """Never write session files into the repo during tests."""
    monkeypatch.setattr(config, "SESSIONS_DIR", str(tmp_path / "sessions"))
    sessions._cache.clear()
    yield
    sessions._cache.clear()
