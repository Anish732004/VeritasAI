"""Every test runs with no OpenAI key and AI switched off, whatever is in the developer's .env.

Without this a real key in .env would make tests call OpenAI (slow, costs money, and results would
depend on the machine). Tests that need AI use a stand-in instead.
"""
import pytest


@pytest.fixture(autouse=True)
def no_real_ai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")  # an empty value stops python-dotenv from loading the real one
    from backend import ai
    monkeypatch.setattr(ai, "OPENAI_API_KEY", "")
    monkeypatch.setattr(ai, "ENABLED", False)
