"""Offline tests for the AI relevance check on search results (the model is replaced by a stand-in)."""
import importlib
import os
import tempfile

import pytest

from backend import ai, search


def paper(i, title, abstract="", total=0.5, foundational=False):
    return {"external_id": f"W{i}", "title": title, "abstract": abstract, "year": "2024", "journal": "Energy",
            "foundational": foundational, "score": {"total": total, "parts": {"coverage": 1, "text": 0.5, "venue": 0.7, "recency": 0.9}}}


def results():
    return [paper(0, "Power plants and AI", "We apply machine learning to coal power plant efficiency.", 0.80),
            paper(1, "Powerful women in tech", "Interviews with powerful leaders about AI hype.", 0.78),
            paper(2, "Solar forecasting", "", 0.60),
            paper(3, "Classic grid paper", "A highly cited study.", 0.9, foundational=True)]


RATINGS = [
    {"i": 0, "level": 3, "reason": "Applies ML to power-plant efficiency.", "quote": "We apply machine learning to coal power plant efficiency."},
    {"i": 1, "level": 0, "reason": "About leaders, not energy.", "quote": "A sentence the paper never contains."},
    {"i": 2, "level": 3, "reason": "Solar forecasting.", "quote": ""},
    {"i": 3, "level": 2, "reason": "Background on grids.", "quote": ""},
]


def test_ratings_rerank_but_never_remove():
    rs = results()
    assert search.apply_ai_relevance(rs, RATINGS, "gpt-test") == 4
    assert len(rs) == 4
    assert [r["title"] for r in rs][:3] == ["Power plants and AI", "Solar forecasting", "Powerful women in tech"]
    assert rs[-1]["foundational"] is True                       # foundational papers stay in their own group, last
    assert rs[2]["ai_relevance"]["label"] == "Likely off-topic"  # sinks to the bottom of its group, but is still shown
    assert rs[0]["score"]["parts"]["ai"] == 1.0 and rs[0]["score"]["total"] == pytest.approx(0.9)


def test_quotes_are_kept_only_when_really_in_the_paper():
    rs = results()
    search.apply_ai_relevance(rs, RATINGS)
    by = {r["external_id"]: r["ai_relevance"] for r in rs}
    assert by["W0"]["quote"].startswith("We apply machine learning")
    assert by["W1"]["quote"] == ""  # invented quote discarded, rating kept


def test_a_paper_without_an_abstract_cannot_be_rated_above_relevant():
    rs = results()
    search.apply_ai_relevance(rs, RATINGS)
    assert next(r for r in rs if r["external_id"] == "W2")["ai_relevance"]["level"] == 2


@pytest.mark.parametrize("bad", [None, "text", {}, [1, "x"], [{"i": 99, "level": 2}], [{"i": 0, "level": 7}],
                                 [{"i": 0, "level": True}], [{"i": "a", "level": 1}], [{"level": 1}]])
def test_unusable_ratings_change_nothing(bad):
    rs = results()
    before = [(r["title"], r["score"]["total"]) for r in rs]
    assert search.apply_ai_relevance(rs, bad) == 0
    assert [(r["title"], r["score"]["total"]) for r in rs] == before
    assert all("ai_relevance" not in r for r in rs)


def test_ai_relevance_sends_question_and_only_titles_and_abstracts(monkeypatch):
    seen = {}

    def fake(task, prompt, **kw):
        seen.update(task=task, prompt=prompt, data=kw["data"], inputs=kw["inputs"])
        return RATINGS, {"model": "gpt-test", "prompt_version": "t"}
    monkeypatch.setattr(ai, "complete_json", fake)
    rs = results()
    out = search.ai_relevance("How is AI used in power generation?", {"ai_note": "AI in power plants", "concept_groups": [
        {"label": "AI", "required": True, "terms": ["ai"]}, {"label": "Energy", "required": False, "terms": ["energy"]}]}, rs)
    assert out["rated"] == 4 and out["off_topic"] == 1 and out["model"] == "gpt-test"
    assert "power generation" in seen["prompt"] and "AI in power plants" in seen["prompt"] and "Concepts papers should cover: AI" in seen["prompt"]
    assert "Powerful women in tech" in seen["data"] and "strict" in seen["task"]
    assert seen["inputs"] == ["W0", "W1", "W2", "W3"]


def test_no_results_means_no_ai_call(monkeypatch):
    monkeypatch.setattr(ai, "complete_json", lambda *a, **k: pytest.fail("should not call the model"))
    assert search.ai_relevance("q", {}, []) == {"rated": 0, "model": None}


# ------------------------------------------------------------- the search route

@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("VERITAS_DB", os.path.join(tempfile.mkdtemp(), "rel.db"))
    from backend import api, config, db
    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(ai)
    importlib.reload(api)
    from fastapi.testclient import TestClient
    return TestClient(api.create_app()), api


def start(c):
    pid = c.post("/api/projects", json={"title": "T", "question": "How is AI used in power generation?"}).json()["id"]
    c.post(f"/api/projects/{pid}/plan")
    assert c.post(f"/api/projects/{pid}/plan/approve").status_code == 200
    return pid


def fake_discover(monkeypatch, api):
    monkeypatch.setattr(api.search, "discover", lambda plan, d, t: {"results": results(), "report": {
        "retrieved": 4, "shown": 4, "removed": {}, "queries": [], "filters": [], "window": "x", "min_tier": "B", "note": ""}})


def test_search_route_adds_ratings_and_logs_the_ai_call(client, monkeypatch):
    c, api = client
    pid = start(c)
    fake_discover(monkeypatch, api)
    monkeypatch.setattr(ai, "available", lambda: True)
    monkeypatch.setattr(ai, "complete_json", lambda *a, **k: (RATINGS, {"model": "gpt-test", "prompt_version": "t", "task": "x", "inputs": []}))
    out = c.post(f"/api/projects/{pid}/search").json()
    assert out["report"]["ai_relevance"]["rated"] == 4 and out["results"][0]["ai_relevance"]["level"] == 3
    ev = next(e for e in c.get("/api/audit").json()["events"] if e["action"] == "Literature search")
    assert ev["ai"]["model"] == "gpt-test" and "AI rated 4" in ev["details"]


def test_search_route_survives_an_ai_failure(client, monkeypatch):
    c, api = client
    pid = start(c)
    fake_discover(monkeypatch, api)
    monkeypatch.setattr(ai, "available", lambda: True)

    def boom(*a, **k):
        raise ai.AIUnavailable("OpenAI rejected the key.")
    monkeypatch.setattr(ai, "complete_json", boom)
    out = c.post(f"/api/projects/{pid}/search").json()
    assert "rejected the key" in out["report"]["ai_relevance_error"]
    assert len(out["results"]) == 4 and "ai_relevance" not in out["results"][0]  # standard ranking, nothing lost


def test_search_without_ai_has_no_ai_fields(client, monkeypatch):
    c, api = client
    pid = start(c)
    fake_discover(monkeypatch, api)
    monkeypatch.setattr(ai, "complete_json", lambda *a, **k: pytest.fail("AI is off"))
    out = c.post(f"/api/projects/{pid}/search").json()
    assert "ai_relevance" not in out["report"] and "ai_relevance_error" not in out["report"]
