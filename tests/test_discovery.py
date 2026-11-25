"""Offline tests: question understanding (rule-based and AI plan validation) and conference papers.

No network and no OpenAI key: the language model and OpenAlex are replaced by stand-ins.
"""
import pytest

from backend import ai, citations, concepts, scholarly, search, verify

ENERGY = "How is AI helping in energy sector, specifically in electricity generation using?"


def required(groups):
    return [g["label"] for g in groups if g["required"]]


# ------------------------------------------------------------- rule-based understanding

def test_adverbs_and_filler_are_not_concepts():
    labels = [g["label"].lower() for g in concepts.rule_based_groups(ENERGY)]
    assert "specifically" not in labels and "using" not in labels
    assert not any("help" in x for x in labels)


def test_energy_question_keeps_all_three_topics_required():
    groups = concepts.rule_based_groups(ENERGY)
    assert required(groups) == ["Artificial intelligence", "Energy", "Electricity generation"]
    assert "power generation" in next(g for g in groups if g["label"] == "Electricity generation")["terms"]


def test_settings_become_optional_once_there_are_two_topics():
    groups = concepts.rule_based_groups("How is machine learning used in manufacturing for predictive maintenance?")
    assert next(g for g in groups if g["label"] == "Manufacturing")["required"] is False
    assert "Predictive maintenance" in required(groups)


def test_real_ly_topics_are_kept():
    assert not concepts.is_adverb("supply") and not concepts.is_adverb("family")
    assert concepts.is_adverb("specifically") and concepts.is_adverb("particularly")


# ------------------------------------------------------------- AI plan validation and prompt

GOOD = {
    "note": "You want to know how AI is applied to generating electricity.",
    "themes": ["Forecasting", "Plant operation"], "subquestions": ["Which methods?"], "inclusion_criteria": ["Peer reviewed"],
    "concept_groups": [
        {"label": "AI", "required": True, "terms": ["artificial intelligence", "machine learning", "AI", "deep learning"]},
        {"label": "Electricity generation", "required": True, "terms": ["power generation", "electricity generation", "power plant"]},
        {"label": "Energy sector", "required": True, "terms": ["energy sector", "utilities"]},
        {"label": "Forecasting", "required": True, "terms": ["load forecasting", "demand prediction"]},
    ],
    "years": 10, "suggested_filters": {"include_conferences": True},
}


def test_validation_caps_required_groups_and_limits_filters_to_the_offered_choices():
    plan = concepts.validate_ai_plan(GOOD)
    assert len(required(plan["concept_groups"])) == 3
    assert plan["filters"]["years"] == 10 and plan["filters"]["include_conferences"] is True
    assert plan["ai_note"].startswith("You want")
    assert concepts.validate_ai_plan({**GOOD, "years": 99})["filters"]["years"] == 5  # not an offered choice
    assert concepts.validate_ai_plan({**GOOD, "years": True})["filters"]["years"] == 5


def test_validation_drops_junk_terms_and_groups():
    bad = {"concept_groups": [
        {"label": "Specifically", "required": True, "terms": ["specifically", "impact", "the study"]},
        {"label": "Solar", "required": False, "terms": ["solar", "Solar", "  photovoltaic ", "x", ""]}]}
    plan = concepts.validate_ai_plan(bad)
    assert [g["label"] for g in plan["concept_groups"]] == ["Solar"]
    assert plan["concept_groups"][0]["terms"] == ["solar", "photovoltaic"]
    assert plan["concept_groups"][0]["required"] is True  # at least one group must be required


def test_validation_rejects_unusable_output():
    for data in ([], {"concept_groups": []}, {"concept_groups": [{"label": "x", "terms": ["impact"]}]}, "text"):
        with pytest.raises(ai.AIUnavailable):
            concepts.validate_ai_plan(data)


def test_ai_plan_sends_scope_and_level_and_labels_the_model(monkeypatch):
    seen = {}

    def fake(task, prompt, **kw):
        seen.update(task=task, prompt=prompt)
        return GOOD, {"model": "gpt-test", "prompt_version": "t"}
    monkeypatch.setattr(ai, "complete_json", fake)
    plan, meta = concepts.ai_plan(ENERGY, "power plants in India", "Postgraduate")
    assert "power plants in India" in seen["prompt"] and "Postgraduate" in seen["prompt"]
    assert "include_conferences" in seen["task"] and "note" in seen["task"]
    assert plan["generated_by"].startswith("AI proposal (gpt-test)") and meta["model"] == "gpt-test"


# ------------------------------------------------------------- conference papers

def test_work_kind():
    assert scholarly.work_kind("conference-paper") == "conference-paper"
    assert scholarly.work_kind("proceedings-article") == "conference-paper"
    assert scholarly.work_kind("article", "conference") == "conference-paper"
    assert scholarly.work_kind("article", "journal") == "journal-article"


def conf(name="IEEE Conf on Things", **kw):
    return {"kind": "conference-paper", "journal": name, "source_id": "S1", **kw}


def source(h=None, c=None, publisher=None, type_="conference"):
    stats = {} if h is None else {"h_index": h, "2yr_mean_citedness": c}
    return {"summary_stats": stats, "host_organization_name": publisher, "type": type_}


IEEE = "Institute of Electrical and Electronics Engineers"


def test_conference_tiers_from_metrics_and_publisher():
    assert search.conference_tier(conf(), source(191, 1.5), [])["tier"] == "A"
    assert search.conference_tier(conf(), source(35, 1.2), [])["tier"] == "B"
    assert search.conference_tier(conf(), source(20, 0.5, IEEE), [])["tier"] == "B"      # recognised publisher
    assert search.conference_tier(conf(), source(20, 0.5, "Unknown Press"), [])["tier"] == "C"
    assert search.conference_tier(conf(), source(5, 0.1, IEEE), [])["tier"] == "C"        # too little track record
    assert search.conference_tier(conf(), source(), [])["tier"] == "Unrated"


def test_proceedings_series_are_capped_even_with_a_high_h_index():
    t = search.conference_tier(conf("E3S Web of Conferences"), source(74, 1.3, "EDP Sciences"), [])
    assert t["tier"] == "C" and "individual conference" in t["basis"]
    assert search.conference_tier(conf("Lecture notes in networks and systems"), source(87, 1.1, "Springer", "book series"), [])["tier"] == "C"


def test_ranked_conference_list_overrides_metrics(tmp_path, monkeypatch):
    f = tmp_path / "conference_list.csv"
    f.write_text("name,list,tier\nAdvances in Neural Information Processing Systems,CORE,A*\nSmall Workshop on Power,CORE,C\n")
    monkeypatch.setattr(search, "CONFERENCE_LIST_PATH", f)
    lst = search.load_conference_list()
    hit = search.conference_tier(conf("Proceedings of the 35th Conference on Advances in Neural Information Processing Systems"), source(5, 0.1), lst)
    assert hit["tier"] == "A" and "CORE A*" in hit["basis"]
    assert search.conference_tier(conf("2022 Small Workshop on Power"), source(191, 5), lst)["tier"] == "C"  # the list wins


def test_venue_tier_uses_conference_path_only_for_conference_papers():
    journal = {"kind": "journal-article", "journal": "Energy", "source_id": "S1", "issn": []}
    t = search.venue_tier(journal, {"S1": {"summary_stats": {"2yr_mean_citedness": 4, "h_index": 100}}}, {})
    assert t["tier"] == "A" and "conference" not in t["basis"].lower()


def test_conference_names_match_across_databases():
    a = "International Conference on Cyber-Physical Social Intelligence (ICCSI)"
    assert verify.compare_journal(a, "2022 " + a, conference=True)["status"] == "match"
    assert verify.compare_journal("Hawaii International Conference on System Sciences",
                                  "Proceedings of the 55th Hawaii International Conference on System Sciences", conference=True)["status"] == "match"
    assert verify.compare_journal("Conference on Solar Power", "Conference on Wind Energy", conference=True)["status"] != "match"
    assert verify.compare_journal("Nature", "Science", conference=True)["status"] == "mismatch"


def test_conference_papers_are_cited_as_conference_papers():
    item = citations.csl_item({"id": "r1", "kind": "conference-paper", "title": "T", "journal": "Proc. of X", "year": "2022", "authors": []})
    assert item["type"] == "paper-conference" and item["container-title"] == "Proc. of X"
    assert citations.csl_item({"id": "r2", "title": "T", "year": "2022", "authors": []})["type"] == "article-journal"


class FakeOpenAlex:
    def __init__(self):
        self.calls = []

    def search(self, query, filters, per_page=50, sort=None):
        self.calls.append(filters)
        return [], 0


@pytest.mark.parametrize("include, expect_conf", [(True, True), (False, False)])
def test_search_filters_follow_the_conference_switch(monkeypatch, include, expect_conf):
    fake = FakeOpenAlex()
    monkeypatch.setattr(scholarly, "openalex_search", fake.search)
    monkeypatch.setattr(scholarly, "openalex_sources", lambda ids: {})
    plan = {"concept_groups": [{"label": "A", "required": True, "terms": ["solar"]}], "filters": {"include_conferences": include}}
    search.discover(plan, set(), set())
    joined = ",".join(fake.calls[0])
    assert ("conference-paper" in joined) is expect_conf
    assert ("source.type:journal|conference" in joined) is expect_conf


def test_old_plans_without_the_setting_include_conferences(monkeypatch):
    fake = FakeOpenAlex()
    monkeypatch.setattr(scholarly, "openalex_search", fake.search)
    monkeypatch.setattr(scholarly, "openalex_sources", lambda ids: {})
    search.discover({"concept_groups": [{"label": "A", "required": True, "terms": ["solar"]}],
                     "filters": {"years": 5, "article_only": True}}, set(), set())
    assert "conference-paper" in ",".join(fake.calls[0])


def test_database_from_before_conferences_is_migrated(tmp_path, monkeypatch):
    import importlib
    import sqlite3

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE refs (id TEXT PRIMARY KEY, project_id TEXT, title TEXT NOT NULL)")
    con.execute("INSERT INTO refs (id, title) VALUES ('r1', 'Old source')")
    con.commit()
    con.close()
    monkeypatch.setenv("VERITAS_DB", str(path))
    from backend import config, db
    importlib.reload(config)
    importlib.reload(db)
    db.init_db()
    with db.db() as c:
        assert c.execute("SELECT kind FROM refs WHERE id = 'r1'").fetchone()["kind"] == "journal-article"


def test_conference_papers_get_inproceedings_bibtex_and_a_review_flag():
    ref = {"id": "r1", "kind": "conference-paper", "title": "Short title", "journal": "Conf on X", "year": "2022", "doi": "10.1/x",
           "authors": [{"given": "A", "family": "Lee"}], "pages": "1-2", "verification_status": "Verified match"}
    bib = citations.bibtex([ref])
    assert bib.startswith("@inproceedings{Lee2022") and "booktitle = {Conf on X}" in bib and "journal" not in bib
    assert any("Conference paper" in f["text"] for f in citations.risk_review(ref, 1))
    assert citations.bibtex([{**ref, "kind": "journal-article"}]).startswith("@article{")
