"""Every test runs with no AI key (NVIDIA or OpenAI) and AI switched off, whatever is in the developer's .env,
and with no network access to OpenAlex or Crossref (except the live suite, VERITAS_LIVE=1).

Without this a real key in .env would make tests call OpenAI (slow, costs money, and results would
depend on the machine). Tests that need AI use a stand-in instead.
"""
import pytest


@pytest.fixture(autouse=True)
def no_real_ai(monkeypatch):
    for var in ("OPENAI_API_KEY", "NVIDIA_API_KEY", "AI_PROVIDER", "NVIDIA_MODEL", "OPENAI_MODEL"):
        monkeypatch.setenv(var, "")  # an empty value stops python-dotenv from loading the real one
    from backend import ai
    for attr in ("OPENAI_API_KEY", "NVIDIA_API_KEY", "AI_PROVIDER"):
        monkeypatch.setattr(ai, attr, "")
    monkeypatch.setattr(ai, "ENABLED", False)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Offline tests must never call OpenAlex or Crossref: it is slow and spends the shared daily allowance.
    A test that needs data replaces the scholarly function it uses with a stand-in."""
    import os
    if os.getenv("VERITAS_LIVE") == "1":
        return
    from backend import scholarly

    def offline(url, *a, **k):
        raise scholarly.ServiceError("OpenAlex/Crossref", "network disabled in offline tests")
    monkeypatch.setattr(scholarly, "fetch_json", offline)

