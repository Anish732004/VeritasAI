"""Planning tests: the rule-based fallback and the validation that protects the search
from whatever a language model returns. The model itself is simulated (no network)."""
import pytest

from backend import ai, concepts


def labels(groups):
    return [g["label"] for g in groups]


def test_rule_based_ignores_filler_words():
    g = concepts.rule_based_groups("How is AI helping in energy sector, specifically in electricity generation using?")
    assert "Specifically" not in labels(g)
    assert labels(g)[:3] == ["Artificial intelligence", "Energy", "Electricity generation"]
    assert all(x["required"] for x in g[:3])


def test_sanitise_cleans_model_output():
    raw = [
        {"label": "  AI   methods ", "required": True,
         "terms": ['"machine learning"', "deep learning (DL)", "AI OR ML", "system", "data", "x", "machine learning"]},
        {"label": "Grid", "required": True, "terms": ["smart grid", "power systems", "grid optimisation"]},
        {"label": "Setting", "required": True, "terms": ["electricity generation"]},
        {"label": "Fourth", "required": True, "terms": ["solar forecasting"]},
        {"label": "Empty", "required": True, "terms": ["", "the", "study"]},
        "not a dict",
    ]
    g = concepts.sanitise_groups(raw)
    assert labels(g) == ["AI methods", "Grid", "Setting", "Fourth"]  # empty group and junk dropped
    assert g[0]["terms"] == ["machine learning", "deep learning DL", "AI ML"]  # quotes, brackets, operators, generic words, duplicates removed
    assert sum(x["required"] for x in g) == 4  # no cap on required groups: the model decides (decision: 2026-11-25)


def test_sanitise_keeps_one_required_group():
    g = concepts.sanitise_groups([{"label": "A", "required": "yes", "terms": ["alpha beta"]}])
    assert g[0]["required"] is True  # "yes" is not a real boolean, so the safety rule promotes it
    assert concepts.sanitise_groups("garbage") == [] and concepts.sanitise_groups(None) == []


def test_ai_plan_uses_model_and_validates(monkeypatch):
    seen = {}

    def fake(task, prompt, **kw):
        seen["prompt"] = prompt
        return ({"concept_groups": [
            {"label": "Machine learning", "required": True, "terms": ["machine learning", "deep learning", "neural network"]},
            {"label": "Power systems", "required": True, "terms": ["power systems", "smart grid", "electricity generation", "renewable energy forecasting"]}],
            "themes": ["Forecasting", "Grid optimisation"], "subquestions": ["Which methods improve generation scheduling?"],
            "inclusion_criteria": ["Peer-reviewed"], "years": 3, "note": "Read 'AI' as machine learning applied to power generation."},
            {"model": "test-model", "prompt_version": "x", "task": "t", "inputs": []})

    monkeypatch.setattr(ai, "complete_json", fake)
    plan, meta = concepts.ai_plan("How is AI helping in energy?", scope="power plants", level="Postgraduate")
    assert "power plants" in seen["prompt"] and "Postgraduate" in seen["prompt"]
    assert plan["generated_by"].startswith("AI proposal (test-model)")
    assert plan["filters"]["years"] == 3 and plan["ai_note"]
    assert labels(plan["concept_groups"]) == ["Machine learning", "Power systems"]


@pytest.mark.parametrize("bad", [[], {}, {"concept_groups": []}, {"concept_groups": [{"label": "x", "terms": ["the", "study"]}]}])
def test_ai_plan_rejects_unusable_output(monkeypatch, bad):
    monkeypatch.setattr(ai, "complete_json", lambda *a, **k: (bad, {"model": "m"}))
    with pytest.raises(ai.AIUnavailable):
        concepts.ai_plan("anything")


def test_bad_years_are_ignored(monkeypatch):
    out = {"concept_groups": [{"label": "A", "required": True, "terms": ["alpha beta"]}], "years": 7}
    monkeypatch.setattr(ai, "complete_json", lambda *a, **k: (out, {"model": "m"}))
    assert concepts.ai_plan("q")[0]["filters"]["years"] == 5
