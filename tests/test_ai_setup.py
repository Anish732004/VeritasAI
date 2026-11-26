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


# ------------------------------------------------------------------ provider choice (NVIDIA or OpenAI)

def use(monkeypatch, nvidia="", openai="", provider=""):
    monkeypatch.setattr(ai, "NVIDIA_API_KEY", nvidia)
    monkeypatch.setattr(ai, "OPENAI_API_KEY", openai)
    monkeypatch.setattr(ai, "AI_PROVIDER", provider)


def test_nvidia_key_selects_nvidia_and_openai_key_selects_openai(monkeypatch):
    use(monkeypatch, nvidia="nvapi-x")
    assert (ai.provider(), ai.api_key(), ai.model()) == ("nvidia", "nvapi-x", ai.NVIDIA_MODEL)
    use(monkeypatch, openai="sk-x")
    assert (ai.provider(), ai.api_key(), ai.model()) == ("openai", "sk-x", ai.OPENAI_MODEL)
    use(monkeypatch, nvidia="nvapi-x", openai="sk-x")
    assert ai.provider() == "nvidia"                                  # NVIDIA preferred when both are set
    use(monkeypatch, nvidia="nvapi-x", openai="sk-x", provider="openai")
    assert ai.provider() == "openai" and ai.api_key() == "sk-x"       # unless AI_PROVIDER says otherwise
    use(monkeypatch)
    assert not ai.configured()


def test_an_nvidia_key_saved_under_the_openai_name_still_goes_to_nvidia(monkeypatch):
    use(monkeypatch, openai="nvapi-misplaced")
    assert ai.misplaced_key() and ai.provider() == "nvidia" and ai.api_key() == "nvapi-misplaced"
    use(monkeypatch, openai="nvapi-misplaced", provider="openai")
    assert ai.api_key() == ""                                         # never send an NVIDIA key to OpenAI


def test_errors_name_the_configured_provider(monkeypatch):
    class AuthenticationError(Exception): pass
    class NotFoundError(Exception): pass
    use(monkeypatch, nvidia="nvapi-x")
    assert "NVIDIA rejected the key" in ai.explain(AuthenticationError()) and "nvapi-" in ai.explain(AuthenticationError())
    assert "NVIDIA_MODEL" in ai.explain(NotFoundError()) and "build.nvidia.com" in ai.explain(NotFoundError())


class FakeClient:
    """Stands in for the OpenAI SDK client: records calls and returns a scripted reply."""
    def __init__(self, content="OK", fail_first=None):
        self.calls, self.content, self.fail_first = [], content, fail_first
        self.chat = self
        self.completions = self

    def create(self, **kw):
        self.calls.append(kw)
        if self.fail_first and len(self.calls) == 1:
            raise self.fail_first
        msg = type("M", (), {"content": self.content})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()], "model": kw["model"]})()


def test_nvidia_requests_switch_thinking_off_and_strip_any_thinking(monkeypatch):
    use(monkeypatch, nvidia="nvapi-x")
    monkeypatch.setattr(ai, "ENABLED", True)
    fake = FakeClient('<think>long private reasoning {"x": 1}</think>```json\n{"ok": true}\n```')
    monkeypatch.setattr(ai, "_client", lambda timeout: fake)
    data, meta = ai.complete_json("task", "prompt")
    assert data == {"ok": True} and meta["provider"] == "NVIDIA" and meta["model"] == ai.NVIDIA_MODEL
    assert fake.calls[0]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert fake.calls[0]["messages"][0]["role"] == "system" and "Never invent references" in fake.calls[0]["messages"][0]["content"]


def test_a_model_without_the_thinking_switch_is_asked_again_without_it(monkeypatch):
    class BadRequestError(Exception): pass
    use(monkeypatch, nvidia="nvapi-x")
    fake = FakeClient("OK", fail_first=BadRequestError())
    monkeypatch.setattr(ai, "_client", lambda timeout: fake)
    assert ai.ping()["reply"] == "OK" and len(fake.calls) == 2 and "extra_body" not in fake.calls[1]


def test_openai_requests_carry_no_nvidia_options(monkeypatch):
    use(monkeypatch, openai="sk-x")
    fake = FakeClient("OK")
    monkeypatch.setattr(ai, "_client", lambda timeout: fake)
    assert ai.ping() == {"ok": True, "provider": "OpenAI", "model": ai.OPENAI_MODEL, "reply": "OK"}
    assert "extra_body" not in fake.calls[0]

