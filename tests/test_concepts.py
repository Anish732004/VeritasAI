"""Offline tests for the rule-based concept map (no AI, no network).

The two benchmark files in tests/data are real-looking research questions with the concepts a
librarian would search for. They guard against a change that helps one question and breaks others.
"""
import importlib
import json
import os
import pathlib
import tempfile

import pytest

from backend import concepts, scholarly, thesaurus
from backend.text import fold

DATA = pathlib.Path(__file__).resolve().parent / "data"


def labels(groups):
    return [g["label"] for g in groups]


def score(cases):
    """(share of expected concepts found, junk groups, questions fully covered)."""
    found = total = junk = full = 0
    for c in cases:
        groups = [g for g in concepts.rule_based_groups(c["q"]) if g["label"] != "Risks & limitations"]
        terms = [{fold(t) for t in g["terms"]} for g in groups]
        hits = [next((i for i, ts in enumerate(terms) if any(a in ts for a in alts)), None) for alts in c["expect"]]
        found += sum(h is not None for h in hits)
        total += len(hits)
        full += None not in hits
        junk += len(set(range(len(groups))) - {h for h in hits if h is not None})
    return found / total, junk, full


@pytest.mark.parametrize("name, min_found, max_junk", [("planning_benchmark.json", 0.95, 3), ("planning_heldout.json", 0.9, 3),
                                                     ("planning_final.json", 0.9, 3)])
def test_benchmarks_do_not_regress(name, min_found, max_junk):
    cases = json.loads((DATA / name).read_text())
    found, junk, full = score(cases)
    assert found >= min_found, f"{name}: only {found:.0%} of expected concepts found"
    assert junk <= max_junk, f"{name}: {junk} groups match no expected concept"


# ------------------------------------------------------------------ parsing rules

def test_verbs_between_concepts_split_them():
    assert labels(concepts.rule_based_groups("Does microfinance reduce poverty?"))[:2] == ["Microfinance", "Poverty"]
    assert "Gamification" in labels(concepts.rule_based_groups("What role does gamification play in learning?"))
    assert "Depression" in labels(concepts.rule_based_groups("Can social media use predict depression?"))


def test_evaluative_words_are_not_concepts():
    got = [l.lower() for l in labels(concepts.rule_based_groups("How effective are large language models in grading student essays?"))]
    assert "effective" not in got and "large language models" in got


def test_soft_heads_complete_a_phrase():
    g = concepts.rule_based_groups("What are the effects of telemedicine on patient outcomes?")
    assert "Patient outcomes" in labels(g)
    g = concepts.rule_based_groups("How does ESG performance affect firm value?")
    esg = next(x for x in g if x["label"] == "ESG performance")
    assert {"ESG performance", "ESG"} <= set(esg["terms"])
    assert "Firm value" in labels(g)                      # "firm" is a modifier here, not a vague noun


def test_two_ideas_in_one_phrase_are_split():
    assert labels(concepts.rule_based_groups("What factors influence electric vehicle adoption?")) == ["Electric vehicles", "Adoption"]
    got = labels(concepts.rule_based_groups("How effective are large language models in grading student essays?"))
    assert "Grading and assessment" in got and "Student essays" in got
    g = concepts.rule_based_groups("How does green HRM influence employee pro-environmental behaviour?")
    assert labels(g)[:2] == ["Green HRM", "Pro-environmental behaviour"]
    assert next(x for x in g if x["label"] == "Employees")["required"] is False   # population = optional setting


def test_a_modifier_stays_with_the_concept_it_qualifies():
    g = concepts.rule_based_groups("Is there a relationship between CEO overconfidence and corporate investment decisions?")
    assert labels(g) == ["Overconfidence", "Investment decisions"]
    assert "corporate investment decisions" in next(x for x in g if x["label"] == "Investment decisions")["terms"]


def test_two_known_concepts_in_a_row_stay_separate():
    assert labels(concepts.rule_based_groups("blockchain supply chain transparency"))[:3] == ["Blockchain", "Supply chain", "Transparency"]


def test_instrument_heads_also_search_the_topic():
    g = concepts.rule_based_groups("How does mindfulness training affect stress?")
    assert {"mindfulness training", "mindfulness"} <= set(g[0]["terms"])


def test_intention_to_is_turned_into_the_usual_term():
    got = labels(concepts.rule_based_groups("What drives consumer intention to purchase organic food?"))
    assert "Purchase intention" in got and "Organic food" in got


def test_capitals_in_the_question_are_kept():
    g = concepts.rule_based_groups("What are the barriers to cloud computing adoption among SMEs?")
    assert "SMEs" in labels(g)
    assert "US" in [t for x in concepts.rule_based_groups("How do tariffs affect trade between the US and China?") for t in x["terms"]]


def test_acronyms_are_expanded_and_plurals_found():
    g = concepts.rule_based_groups("How can IoT improve predictive maintenance?")
    assert {"Internet of Things", "IoT"} <= set(g[0]["terms"])
    assert concepts.rule_based_groups("Do chatbots help?")[0]["label"] == "Chatbots"


def test_each_group_says_where_its_terms_came_from():
    g = concepts.rule_based_groups("Does microfinance reduce poverty among cyberbullied orchids?")
    src = {x["label"]: x["source"] for x in g}
    assert src["Microfinance"] == "thesaurus" and src["Cyberbullied orchids"] == "question"


def test_possessives_split_people_from_their_topic_but_not_disease_names():
    g = concepts.rule_based_groups("What factors influence nurses' turnover intention in public hospitals?")
    assert "Turnover intention" in labels(g) and next(x for x in g if x["label"] == "Nurses")["required"] is False
    assert labels(concepts.rule_based_groups("Does exercise slow Alzheimer's disease progression?")) == ["Exercise", "Alzheimer's disease progression"]
    assert "Empowerment" in labels(concepts.rule_based_groups("How does microfinance affect women's empowerment?"))


def test_numbers_stay_inside_a_phrase():
    assert "Type 2 diabetes" in labels(concepts.rule_based_groups("Can wearable devices improve self-management of type 2 diabetes?"))


def test_places_and_populations_are_optional_settings():
    g = concepts.rule_based_groups("Do mobile banking apps increase financial inclusion in sub-Saharan Africa?")
    assert labels(g) == ["Mobile banking apps", "Financial inclusion", "Sub-Saharan Africa"]   # not swallowed by "banking"
    assert [x["required"] for x in g] == [True, True, False]
    assert next(x for x in concepts.rule_based_groups("advertising and impulse buying among young consumers")
                if x["label"] == "Young consumers")["required"] is False


def test_a_known_concept_in_front_of_other_content_is_its_own_idea():
    assert labels(concepts.rule_based_groups("How effective are AI tutoring systems for mathematics learning?"))[:2] == \
        ["Artificial intelligence", "Tutoring systems"]
    assert labels(concepts.rule_based_groups("How does ESG performance affect firm value?"))[0] == "ESG performance"


def test_unknown_three_word_phrases_also_search_their_core():
    g = concepts.rule_based_groups("How do tariffs affect international trade flows?")
    assert {"international trade flows", "trade flows"} <= set(g[1]["terms"])


# ------------------------------------------------------------------ thesaurus hygiene

def test_thesaurus_entries_are_well_formed():
    for key, (label, terms) in thesaurus.SYNONYMS.items():
        assert key == key.lower() and label and terms, key
        assert len({t.lower() for t in terms}) == len(terms), f"duplicate terms in {key}"
    for key, (short, long) in thesaurus.ACRONYMS.items():
        assert key == key.lower() and short.lower() == key


def test_no_term_contains_a_comma():
    """The plan editor separates terms with commas, so a comma inside a term would split it."""
    every = [t for _, ts in thesaurus.SYNONYMS.values() for t in ts] + [x for pair in thesaurus.ACRONYMS.values() for x in pair]
    assert not [t for t in every if "," in t]
    for f in ("planning_benchmark.json", "planning_heldout.json", "planning_final.json"):
        for c in json.loads((DATA / f).read_text()):
            assert not [t for g in concepts.rule_based_groups(c["q"]) for t in g["terms"] if "," in t], c["q"]


# ------------------------------------------------------------------ OpenAlex suggestions

COUNTS = {"telehealth": 9, "telemedicine regulation": 7, "covid-19 pandemic": 6, "telemedicine": 25, "primary care": 2,
          "impact": 5, "virtual care": 4}


def test_related_candidates_keep_real_alternatives_only():
    out = concepts.related_candidates("telemedicine", ["telemedicine"], COUNTS, 25)
    terms = [x["term"] for x in out]
    assert terms == ["telehealth", "covid-19 pandemic", "virtual care"]   # ranked by how many papers carry them
    assert out[0] == {"term": "telehealth", "papers": 9, "of": 25}
    assert concepts.related_candidates("telemedicine", [], COUNTS, 6) == []  # too few papers to judge


def test_suggestions_only_for_unknown_required_concepts_and_never_added_to_terms():
    groups = concepts.rule_based_groups("Does microfinance reduce cyberbullying?")
    asked = []

    def fake(phrase):
        asked.append(phrase)
        return {"online harassment": 8, "cyber victimization": 6}, 25
    concepts.add_suggestions(groups, fake)
    assert asked == ["cyberbullying"]                                   # microfinance is in the thesaurus
    cb = next(g for g in groups if g["label"] == "Cyberbullying")
    assert [s["term"] for s in cb["suggestions"]] == ["online harassment", "cyber victimization"]
    assert cb["terms"] == ["cyberbullying"]


def test_suggestions_fail_quietly_and_respect_the_lookup_limit():
    groups = [{"label": f"T{i}", "terms": [f"t{i}"], "required": True, "source": "question"} for i in range(6)]

    def boom(phrase):
        raise scholarly.ServiceError("OpenAlex", "rate limited", 429)
    assert concepts.add_suggestions(groups, boom) == 0 and not any("suggestions" in g for g in groups)
    calls = []
    concepts.add_suggestions(groups, lambda p: (calls.append(p) or ({}, 25)), max_lookups=4)
    assert len(calls) == 4


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("VERITAS_DB", os.path.join(tempfile.mkdtemp(), "c.db"))
    from backend import ai, api, config, db
    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(ai)
    importlib.reload(api)
    from fastapi.testclient import TestClient
    return TestClient(api.create_app()), api


def test_generated_plan_carries_suggestions_and_edits_keep_them(client, monkeypatch):
    c, api = client
    monkeypatch.setattr(api.scholarly, "openalex_keyword_counts", lambda phrase: ({"online harassment": 8}, 25))
    pid = c.post("/api/projects", json={"title": "T", "question": "How does cyberbullying relate to self-esteem in teenagers?"}).json()["id"]
    plan = c.post(f"/api/projects/{pid}/plan").json()
    assert plan["generated_by"].startswith("Rule-based plan")
    cb = next(g for g in plan["concept_groups"] if g["label"] == "Cyberbullying")
    assert cb["source"] == "question" and cb["suggestions"][0]["term"] == "online harassment"
    edited = [{**g, "terms": g["terms"] + (["online harassment"] if g["label"] == "Cyberbullying" else [])} for g in plan["concept_groups"]]
    saved = c.put(f"/api/projects/{pid}/plan", json={"concept_groups": [{k: g[k] for k in ("label", "terms", "required")} for g in edited],
                                                     "filters": plan["filters"]}).json()
    cb2 = next(g for g in saved["concept_groups"] if g["label"] == "Cyberbullying")
    assert "online harassment" in cb2["terms"] and cb2["suggestions"] and cb2["source"] == "question"


def test_plan_generation_works_when_openalex_is_unavailable(client, monkeypatch):
    c, api = client

    def down(phrase):
        raise scholarly.ServiceError("OpenAlex", "budget used up", 429)
    monkeypatch.setattr(api.scholarly, "openalex_keyword_counts", down)
    pid = c.post("/api/projects", json={"title": "T", "question": "How does cyberbullying relate to self-esteem?"}).json()["id"]
    r = c.post(f"/api/projects/{pid}/plan")
    assert r.status_code == 200 and labels(r.json()["concept_groups"])[:2] == ["Cyberbullying", "Self-esteem"]
