"""Offline tests for the AI setup help: plain-language errors and the connection test."""
import importlib
import os
import tempfile

import pytest

from backend import ai


def test_errors_are_explained_in_plain_language():
    class AuthenticationError(Exception): pass
    class RateLimitError(Exception): pass
    class NotFoundError(Exception): pass
    class Weird(Exception): pass
    assert "rejected the key" in ai.explain(AuthenticationError())
    assert "credit" in ai.explain(RateLimitError()) and "ChatGPT" in ai.explain(RateLimitError())
    assert "OPENAI_MODEL" in ai.explain(NotFoundError())
    assert ai.explain(Weird()) == "AI request failed (Weird)"


def test_ping_needs_a_key(monkeypatch):
    monkeypatch.setattr(ai, "OPENAI_API_KEY", "")
    with pytest.raises(ai.AIUnavailable, match=".env"):
        ai.ping()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("VERITAS_DB", os.path.join(tempfile.mkdtemp(), "setup.db"))
    from backend import api, config, db
    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(ai)
    importlib.reload(api)
    from fastapi.testclient import TestClient
    return TestClient(api.create_app()), ai


def test_connection_test_route(client, monkeypatch):
    c, ai_mod = client
    r = c.post("/api/settings/ai/test")
    assert r.status_code == 400 and ".env" in r.json()["detail"]
    monkeypatch.setattr(ai_mod, "ping", lambda: {"ok": True, "model": "gpt-test", "reply": "OK"})
    assert c.post("/api/settings/ai/test").json() == {"ok": True, "model": "gpt-test", "reply": "OK"}
