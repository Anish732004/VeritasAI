"""Regression tests for the issues a teammate reported in review (2026-11-26). All offline.

1 titles with changed words passed as Verified    4 backups could not be restored
2 duplicates in the bibliography / BibTeX keys    5 demo or other-project sources could be linked as evidence
3 author names with trailing honours split wrongly 6 blank input, stale plan, Red Team stance, phone layout
"""
import importlib
import os
import pathlib
import tempfile

import pytest

from backend import citations, redteam, scholarly, verify
from backend.text import parse_person_name

ROOT = pathlib.Path(__file__).resolve().parent.parent
REAL = "Inclusion in global virtual teams: Exploring non-spatial proximity and knowledge sharing on innovation"


# ------------------------------------------------------------------ 1. titles

@pytest.mark.parametrize("changed", [
    REAL.replace("knowledge sharing", "knowledge hiding"),      # the reported case
    REAL.replace("Exploring", "Destroying"),
    REAL.replace("global", "local"),
    REAL.replace("innovation", "performance"),
    REAL + " in firms",
    "Inclusion in global teams: Exploring non-spatial proximity and knowledge sharing on innovation",
])
def test_a_changed_word_is_never_a_verified_title(changed):
    r = verify.compare_title(changed, REAL)
    assert r["status"] in ("partial", "mismatch")
    assert "differ" in r["note"] or "only in" in r["note"]


@pytest.mark.parametrize("same", [
    REAL.lower(), REAL.upper(), REAL + ".", REAL.replace(": ", " - "), REAL.replace("non-spatial", "non spatial"),
    "<i>Inclusion</i> in global virtual teams: Exploring non‑spatial proximity and knowledge sharing on innovation",
])
def test_case_punctuation_hyphens_and_markup_do_not_matter(same):
    assert verify.compare_title(same, REAL)["status"] == "match"


def test_the_changed_words_are_named_and_unrelated_titles_are_a_mismatch():
    note = verify.compare_title(REAL.replace("sharing", "hiding"), REAL)["note"]
    assert "hiding" in note and "sharing" in note
    assert verify.compare_title("A totally unrelated paper about birds in Peru", REAL)["status"] == "mismatch"
    assert verify.compare_title(REAL.split(":")[0], REAL)["note"].startswith("Main title matches")


def test_a_reference_with_a_changed_title_is_not_verified_overall():
    rec = {"title": REAL, "authors": [{"given": "Shiu-Wan", "family": "Hung"}], "year": "2021", "years": ["2021"],
           "doi": "10.1016/j.jbusres.2020.11.022", "journal": "Journal of Business Research", "issn": []}
    ref = {**rec, "title": REAL.replace("sharing", "hiding")}
    status, _ = verify.overall(verify.compare(ref, rec))
    assert status == verify.STATUS_PARTIAL


# ------------------------------------------------------------------ 3. author names

@pytest.mark.parametrize("raw, given, family", [
    ("Alyas Ahmed, D. R. B. D. P. B.", "Alyas", "Ahmed"),       # the reported case: honours after the name
    ("Alyas Ahmed, DRBDPB", "Alyas", "Ahmed"),
    ("Dato' Seri Ahmad Zaki, D.S.P.N.", "Ahmad", "Zaki"),
    ("Jane Doe, PhD", "Jane", "Doe"),
    ("Smith, John, Jr.", "John", "Smith"),
    ("Hung, Shiu-Wan", "Shiu-Wan", "Hung"),
    ("Smith, J. R.", "J. R.", "Smith"),                          # normal "Family, initials" is untouched
    ("Garcia Marquez, Gabriel", "Gabriel", "Garcia Marquez"),
    ("Dr. Jan van der Berg", "Jan", "van der Berg"),
    ("Madonna", "", "Madonna"),
])
def test_names_are_split_correctly(raw, given, family):
    assert parse_person_name(raw) == (given, family)
    assert scholarly.split_name(raw) == {"given": given, "family": family}


def test_honours_do_not_become_part_of_the_cited_name():
    ref = {"id": "r", "title": "T", "year": "2020", "journal": "J", "authors": [scholarly.split_name("Alyas Ahmed, D. R. B. D. P. B.")]}
    text = citations.bibliography([ref], "APA 7")[0]["text"]
    assert text.startswith("Ahmed, A.") and "D. R. B." not in text


# ------------------------------------------------------------------ test app factory

@pytest.fixture()
def make_client(monkeypatch):
    def factory():
        monkeypatch.setenv("VERITAS_DB", os.path.join(tempfile.mkdtemp(), "t.db"))
        from backend import ai, api, config, db
        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(ai)
        importlib.reload(api)
        from fastapi.testclient import TestClient
        return TestClient(api.create_app()), db
    return factory


def add_ref(db, pid, rid, title=REAL, doi="10.1016/j.jbusres.2020.11.022", status="Verified match", decision="Accepted",
            created="2026-01-01", family="Hung", year="2021", demo=0):
    with db.db() as con:
        db.insert(con, "refs", {"id": rid, "project_id": pid, "title": title, "authors": [{"given": "S", "family": family}],
                                "year": year, "doi": doi, "journal": "Journal of Business Research", "decision": decision,
                                "verification_status": status, "created_at": created, "updated_at": created, "demo": demo,
                                "abstract": "Knowledge sharing boosts innovation in virtual teams."})


def new_project(c, title="P", question="Does knowledge sharing improve innovation in teams?", approve=True):
    """A project with an approved plan (the app only allows claims after the plan checkpoint)."""
    pid = c.post("/api/projects", json={"title": title, "question": question}).json()["id"]
    if approve:
        c.post(f"/api/projects/{pid}/plan")
        assert c.post(f"/api/projects/{pid}/plan/approve").status_code == 200
    return pid


# ------------------------------------------------------------------ 2. duplicates

def test_the_same_paper_saved_three_times_is_listed_once_with_one_key(make_client):
    c, db = make_client()
    pid = new_project(c)
    for i, status in enumerate(("Partial match", "Verified match", "Verified match")):
        add_ref(db, pid, f"r{i}", status=status, created=f"2026-01-0{i + 1}", doi=f"10.1016/J.JBUSRES.2020.11.022" if i == 1 else "10.1016/j.jbusres.2020.11.022")
        with db.db() as con:
            con.execute("UPDATE refs SET override_reason = 'x' WHERE id = ?", (f"r{i}",))
    b = c.get(f"/api/projects/{pid}/bibliography").json()
    assert len(b["entries"]) == 1
    assert b["entries"][0]["reference_id"] == "r1"                  # the best-checked, earliest copy
    assert sum("duplicate" in x["why"] for x in b["excluded"]) == 2
    bib = c.get(f"/api/projects/{pid}/export", params={"fmt": "bib"}).text
    assert bib.count("@article{") == 1 and bib.count("Hung2021") == 1


def test_different_papers_with_the_same_author_and_year_get_distinct_keys_and_suffixes():
    base = {"year": "2021", "journal": "JBR", "authors": [{"given": "S", "family": "Hung"}], "verification_status": "Verified match"}
    refs = [{**base, "id": "a", "title": "Second paper", "doi": "10.1/b"}, {**base, "id": "b", "title": "First paper", "doi": "10.1/a"}]
    assert citations.bibtex_keys(refs) == {"b": "Hung2021a", "a": "Hung2021b"}
    entries = citations.bibliography(refs, "APA 7")
    assert [e["in_text"] for e in entries] == ["(Hung, 2021a)", "(Hung, 2021b)"]
    assert "(2021a)" in entries[0]["text"] and "(2021b)" in entries[1]["text"]
    assert len({k for k in citations.bibtex_keys(refs).values()}) == 2
    assert citations.bibtex(refs).count("@article{Hung2021") == 2 and "Hung2021a," in citations.bibtex(refs)


def test_bibtex_keys_survive_accents_and_missing_data():
    keys = citations.bibtex_keys([{"id": "a", "authors": [{"family": "Müller"}], "year": "2020", "title": "x"},
                                  {"id": "b", "authors": [], "year": "", "title": "y"}])
    assert keys == {"a": "Muller2020", "b": "anonnd"}


def test_dedupe_falls_back_to_the_title_without_a_doi():
    a = {"id": "a", "title": "A Study of Things", "doi": "", "created_at": "1"}
    b = {"id": "b", "title": "a study of  things.", "doi": "", "created_at": "2"}
    c_ = {"id": "c", "title": "Another study", "doi": "", "created_at": "3"}
    kept, dropped = citations.dedupe([a, b, c_])
    assert [r["id"] for r in kept] == ["a", "c"] and dropped[0][0]["id"] == "b"


def test_adding_the_same_reference_twice_by_hand_is_refused(make_client):
    c, _ = make_client()
    pid = new_project(c)
    body = {"project_id": pid, "title": REAL, "authors": "Hung, Shiu-Wan", "year": "2021", "doi": "10.1016/j.jbusres.2020.11.022"}
    assert c.post("/api/references", json=body).status_code == 200
    again = c.post("/api/references", json={**body, "doi": "https://doi.org/10.1016/J.JBUSRES.2020.11.022"})
    assert again.status_code == 409 and "Already in this project" in again.json()["detail"]
    assert c.post("/api/references", json={**body, "doi": "", "title": REAL.upper()}).status_code == 409


# ------------------------------------------------------------------ 4. backup restore

def test_a_backup_restores_into_a_fresh_workspace(make_client):
    a, db_a = make_client()
    pid = new_project(a, "Energy", "How is AI used in electricity generation?")
    add_ref(db_a, pid, "r1")
    cid = a.post(f"/api/projects/{pid}/claims", json={"text": "Knowledge sharing boosts innovation in virtual teams."}).json()["id"]
    assert a.post(f"/api/claims/{cid}/evidence", json={"reference_id": "r1", "passage": "Knowledge sharing boosts innovation in virtual teams."}).status_code == 200
    a.put(f"/api/projects/{pid}/disclosure", json={"text": "My own wording."})
    a.put("/api/settings/ai", json={"enabled": True})  # refused (no key), so nothing to carry over
    backup = a.get("/api/backup").json()
    assert backup["format"] == "veritas-backup"

    b, db_b = make_client()                              # a brand-new computer
    r = b.post("/api/restore", json=backup).json()
    assert (r["projects"], r["references"], r["claims"], r["evidence"]) == (1, 1, 1, 1)
    assert r["skipped"]["demo"] == 1                    # the sample project is not carried over
    bundle = b.get(f"/api/projects/{pid}").json()
    assert bundle["project"]["title"] == "Energy" and len(bundle["references"]) == 1
    claim = bundle["claims"][0]
    assert claim["status"] == "Source-supported" and claim["evidence"][0]["reference_id"] == "r1"  # links survived
    assert b.get(f"/api/projects/{pid}/disclosure").json()["saved"] == "My own wording."
    assert any(e["action"] == "Backup restored" for e in b.get("/api/audit").json()["events"])


def test_restoring_twice_changes_nothing_and_existing_projects_are_untouched(make_client):
    a, db_a = make_client()
    pid = new_project(a)
    add_ref(db_a, pid, "r1")
    backup = a.get("/api/backup").json()
    a.patch(f"/api/projects/{pid}", json={"title": "Edited after the backup"})
    again = a.post("/api/restore", json=backup).json()
    assert again["projects"] == 0 and again["skipped"]["already here"] == 1
    assert a.get(f"/api/projects/{pid}").json()["project"]["title"] == "Edited after the backup"
    b, _ = make_client()
    assert b.post("/api/restore", json=backup).json()["projects"] == 1
    assert b.post("/api/restore", json=backup).json()["projects"] == 0
    assert len(b.get(f"/api/projects/{pid}").json()["references"]) == 1


def test_restore_never_switches_ai_on_and_ignores_unknown_columns(make_client):
    a, _ = make_client()
    pid = new_project(a)
    backup = a.get("/api/backup").json()
    backup["settings"] = [{"key": "ai_enabled", "value": "true"}, {"key": "name", "value": "\"Mallory\""}]
    backup["projects"][0]["evil; DROP TABLE refs; --"] = "x"
    b, db_b = make_client()
    assert b.post("/api/restore", json=backup).status_code == 200
    from backend import ai
    assert ai.ENABLED is False and b.get("/api/status").json()["ai_enabled"] is False
    assert b.get("/api/status").json()["name"] == "Researcher"
    with db_b.db() as con:
        assert con.execute("SELECT COUNT(*) FROM refs WHERE demo = 0").fetchone()[0] == 0  # the evil column did nothing
        assert con.execute("SELECT 1 FROM projects WHERE id = ?", (pid,)).fetchone()


def test_a_backup_is_not_imported_as_empty_projects_by_the_old_import(make_client):
    a, db_a = make_client()
    pid = new_project(a)
    add_ref(db_a, pid, "r1")
    backup = a.get("/api/backup").json()
    b, _ = make_client()
    r = b.post("/api/import/legacy", json=backup).json()
    assert r["restored"] is True and r["references"] == 1
    assert len(b.get(f"/api/projects/{pid}").json()["references"]) == 1


@pytest.mark.parametrize("bad", ["not json at all", "[1, 2]", '{"projects": []}', '{"hello": 1}'])
def test_restore_rejects_files_that_are_not_backups(make_client, bad):
    c, _ = make_client()
    assert c.post("/api/restore", content=bad, headers={"content-type": "application/json"}).status_code == 400


# ------------------------------------------------------------------ 5. evidence links

def test_a_claim_cannot_cite_a_source_from_another_project_or_demo_data(make_client):
    c, db = make_client()
    p1, p2 = new_project(c, "One"), new_project(c, "Two")
    add_ref(db, p1, "mine")
    add_ref(db, p2, "theirs", title="Another paper entirely", doi="10.2/x")
    with db.db() as con:
        demo_ref = con.execute("SELECT id FROM refs WHERE demo = 1").fetchone()["id"]
    cid = c.post(f"/api/projects/{p1}/claims", json={"text": "Knowledge sharing boosts innovation."}).json()["id"]
    passage = "Knowledge sharing boosts innovation in virtual teams."
    other = c.post(f"/api/claims/{cid}/evidence", json={"reference_id": "theirs", "passage": passage})
    assert other.status_code == 400 and "different project" in other.json()["detail"]
    demo = c.post(f"/api/claims/{cid}/evidence", json={"reference_id": demo_ref, "passage": passage})
    assert demo.status_code == 400 and "Demo" in demo.json()["detail"]
    assert c.get(f"/api/claims/{cid}/suggest", params={"reference_id": "theirs"}).status_code == 400
    assert c.post(f"/api/claims/{cid}/evidence", json={"reference_id": "mine", "passage": passage}).status_code == 200  # own source still fine
    assert c.get(f"/api/claims/{cid}/suggest", params={"reference_id": "mine"}).status_code == 200


def test_demo_claims_still_link_to_demo_sources_only(make_client):
    c, db = make_client()
    p1 = new_project(c)
    add_ref(db, p1, "real")
    with db.db() as con:
        d = con.execute("SELECT c.id AS cid, r.id AS rid FROM claims c JOIN refs r ON r.project_id = c.project_id WHERE c.demo = 1 AND r.demo = 1 LIMIT 1").fetchone()
    ok = c.post(f"/api/claims/{d['cid']}/evidence", json={"reference_id": d["rid"], "passage": "an illustrative demo passage"})
    assert ok.status_code == 200
    assert c.post(f"/api/claims/{d['cid']}/evidence", json={"reference_id": "real", "passage": "an illustrative demo passage"}).status_code == 400


# ------------------------------------------------------------------ 6i. blank input

@pytest.mark.parametrize("body", [{"title": "   ", "question": "A real question here?"}, {"title": "OK", "question": "      "},
                                  {"title": "", "question": "A real question here?"}, {"title": "OK", "question": "ab  "}])
def test_blank_or_space_only_projects_are_refused(make_client, body):
    c, _ = make_client()
    assert c.post("/api/projects", json=body).status_code == 422


def test_blank_edits_and_texts_are_refused_and_good_ones_are_trimmed(make_client):
    c, db = make_client()
    pid = new_project(c)
    assert c.patch(f"/api/projects/{pid}", json={"title": "   "}).status_code == 422
    assert c.patch(f"/api/projects/{pid}", json={"question": "     "}).status_code == 422
    assert c.post(f"/api/projects/{pid}/claims", json={"text": "        "}).status_code == 422
    add_ref(db, pid, "r1")
    assert c.post("/api/references", json={"project_id": pid, "title": "   "}).status_code == 422
    assert c.post("/api/references/r1/fulltext/text", json={"text": " " * 80}).status_code == 422
    assert c.post(f"/api/projects/{pid}/ask", json={"question": "   "}).status_code == 422
    new = c.post("/api/projects", json={"title": "  Padded  ", "question": "   A real question here?   "}).json()["id"]
    p = c.get(f"/api/projects/{new}").json()["project"]
    assert (p["title"], p["question"]) == ("Padded", "A real question here?")


# ------------------------------------------------------------------ 6ii. stale plan

def test_an_old_plan_cannot_be_approved_after_the_question_changes(make_client):
    c, _ = make_client()
    pid = new_project(c, "Banks", "How do banks manage liquidity risk?", approve=False)
    c.post(f"/api/projects/{pid}/plan")
    c.patch(f"/api/projects/{pid}", json={"question": "Does AI personalisation improve ecommerce loyalty?"})
    blocked = c.post(f"/api/projects/{pid}/plan/approve")
    assert blocked.status_code == 409 and "Regenerate" in blocked.json()["detail"]
    assert c.get(f"/api/projects/{pid}").json()["project"]["plan_approved_at"] is None
    plan = c.post(f"/api/projects/{pid}/plan").json()                 # regenerate for the new question
    assert plan["for_question"] == "Does AI personalisation improve ecommerce loyalty?"
    assert c.post(f"/api/projects/{pid}/plan/approve").status_code == 200


def test_changing_the_question_back_makes_the_plan_valid_again_and_edits_keep_the_link(make_client):
    c, _ = make_client()
    pid = new_project(c, "Banks", "How do banks manage liquidity risk?", approve=False)
    plan = c.post(f"/api/projects/{pid}/plan").json()
    c.put(f"/api/projects/{pid}/plan", json={"concept_groups": plan["concept_groups"], "filters": plan["filters"]})  # student edits
    c.patch(f"/api/projects/{pid}", json={"question": "Something else entirely here?"})
    assert c.post(f"/api/projects/{pid}/plan/approve").status_code == 409
    c.patch(f"/api/projects/{pid}", json={"question": "How do banks manage liquidity risk?"})
    assert c.post(f"/api/projects/{pid}/plan/approve").status_code == 200


# ------------------------------------------------------------------ 6iii. Red Team without AI

CLAIM = "AI personalisation improves customer satisfaction in online shopping."


@pytest.mark.parametrize("sentence, expected", [
    ("Personalised recommendations significantly increased customer satisfaction among online shoppers.", "supports"),
    ("AI personalization enhanced customer satisfaction and loyalty in online retail shopping.", "supports"),
    ("Personalization did not significantly improve customer satisfaction in online shopping.", "challenges"),
    ("Intrusive personalisation reduced customer satisfaction and trust among online shoppers.", "challenges"),
    ("Personalisation improves satisfaction, but only when customers perceive low privacy risk in online shopping.", "qualifies"),
    ("We surveyed 300 shoppers in India.", "unclear"),
    ("Privacy concerns reduce adoption of voice assistants.", "unclear"),      # about a different topic
])
def test_rule_based_stance_compares_the_finding_with_the_claim(sentence, expected):
    assert redteam.rule_stance(sentence, CLAIM) == expected


def test_a_decrease_claim_is_supported_by_a_decrease():
    claim = "Intrusive personalisation reduces customer trust."
    assert redteam.rule_stance("Intrusive personalisation significantly reduced customer trust.", claim) == "supports"
    assert redteam.rule_stance("Intrusive personalisation increased customer trust.", claim) == "challenges"


def test_supports_results_are_kept_and_sorted_after_challenges(monkeypatch):
    works = [{"title": "A", "doi": "10.1/a", "abstract": "Personalised recommendations significantly increased customer satisfaction among online shoppers."},
             {"title": "B", "doi": "10.1/b", "abstract": "Personalization did not significantly improve customer satisfaction in online shopping."},
             {"title": "C", "doi": "10.1/c", "abstract": "We surveyed three hundred shoppers about their habits."}]
    monkeypatch.setattr(scholarly, "openalex_search", lambda *a, **k: (works, 3))
    out = redteam.search_counter_evidence({"text": CLAIM}, set())
    assert [r["stance"] for r in out["results"]] == ["challenges", "supports", "unclear"]
    assert "claim" in out["results"][0]["stance_method"]


def test_without_a_claim_the_old_cue_behaviour_remains():
    assert redteam.rule_stance("Personalisation did not improve satisfaction.") == "challenges"
    assert redteam.rule_stance("However, the effect depends on privacy concern.") == "qualifies"
    assert redteam.rule_stance("We surveyed 300 shoppers in India.") == "unclear"


# ------------------------------------------------------------------ 6iv. phone layout (static checks)

def test_verification_centre_has_no_fixed_column_grid_that_overflows_phones():
    js = (ROOT / "static/js/views/verification.js").read_text()
    assert "grid-template-columns" not in js                # the inline 5-column grid overrode the responsive CSS
    css = (ROOT / "static/css/style.css").read_text()
    assert ".metrics.five" in css and "max-width: 560px" in css
    assert "stackable" in (ROOT / "static/js/views/source.js").read_text() and "table.stackable" in css
