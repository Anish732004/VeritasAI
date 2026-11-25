"""Offline tests for the governance controls: policy document, disclosure, AI consent,
data removal and the disclosure in exports. Uses a throwaway database; no network."""
import importlib
import os
import pathlib
import tempfile

import pytest

from backend import governance

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_every_risk_is_in_governance_md():
    doc = (ROOT / "GOVERNANCE.md").read_text()
    missing = [r["risk"] for r in governance.RISKS if r["risk"] not in doc]
    assert not missing, f"GOVERNANCE.md is out of date; missing: {missing}"
    assert all(r["response"] and r["status"] in ("In place", "Partly") for r in governance.RISKS)


BASE = {"searches": 2, "verified": 5, "passages": 3, "challenged": 1, "decisions": 8,
        "ai_calls": 0, "ai_tasks": [], "ai_models": []}


def test_disclosure_without_ai_says_so():
    text = governance.disclosure(BASE)
    assert "No generative AI model was used" in text
    assert "5 reference(s)" in text and "3 supporting passage(s)" in text
    assert "take responsibility" in text


def test_disclosure_lists_recorded_ai_use():
    text = governance.disclosure({**BASE, "ai_calls": 4, "ai_tasks": ["Plan proposed", "Research assistant consulted"],
                                  "ai_models": ["gpt-4.1-mini"]})
    assert "gpt-4.1-mini" in text and "4 time(s)" in text
    assert "proposing search concepts" in text and "research assistant" in text
    assert "No generative AI" not in text


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("VERITAS_DB", os.path.join(tempfile.mkdtemp(), "gov.db"))
    from backend import config, db, ai, api
    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(ai)
    importlib.reload(api)
    from fastapi.testclient import TestClient
    return TestClient(api.create_app()), db, ai


def _seed(db, pid):
    """A project with one accepted, verified source whose full text holds the linked passage."""
    passage = "Personalised recommendations increased repeat purchases among returning customers in the sample."
    with db.db() as con:
        db.insert(con, "refs", {"id": "r1", "project_id": pid, "title": "A real study", "authors": [{"given": "A", "family": "Author"}],
                                "year": "2022", "doi": "10.1000/test", "journal": "Journal of Tests", "abstract": "",
                                "fulltext": "[PDF page 1]\nIntroduction. " + passage + " More text follows here.",
                                "fulltext_origin": "Uploaded PDF (test.pdf)", "decision": "Accepted",
                                "verification_status": "Verified match", "created_at": db.now(), "updated_at": db.now()})
        db.insert(con, "claims", {"id": "c1", "project_id": pid, "text": "Personalisation increases repeat purchases.",
                                  "decision": "Accepted", "created_at": db.now(), "updated_at": db.now()})
        db.insert(con, "evidence_records", {"id": "e1", "claim_id": "c1", "reference_id": "r1", "passage": passage,
                                            "location": "full text", "match": "exact", "stance": "supports", "created_at": db.now()})


def test_ai_stays_off_until_turned_on(client, monkeypatch):
    c, db, ai = client
    assert c.get("/api/status").json()["ai"] is False
    assert c.put("/api/settings/ai", json={"enabled": True}).status_code == 400  # no key configured
    monkeypatch.setattr(ai, "OPENAI_API_KEY", "sk-test")
    s = c.get("/api/status").json()
    assert s["ai_key"] is True and s["ai"] is False  # a key alone does not switch AI on
    assert c.put("/api/settings/ai", json={"enabled": True}).json()["ai"] is True
    assert c.put("/api/settings/ai", json={"enabled": False}).json()["ai"] is False
    actions = [e["action"] for e in c.get("/api/audit").json()["events"]]
    assert "AI features turned on" in actions and "AI features turned off" in actions


def test_governance_endpoint(client):
    c, _, _ = client
    g = c.get("/api/governance").json()
    assert len(g["risks"]) == len(governance.RISKS) and g["checks"] and g["accountability"]
    assert "Never invent references" in g["model_instructions"]


def test_remove_stored_text_rechecks_claims(client):
    c, db, _ = client
    pid = c.post("/api/projects", json={"title": "T", "question": "Does personalisation work?"}).json()["id"]
    _seed(db, pid)
    r = c.delete("/api/references/r1/fulltext")
    assert r.status_code == 200 and r.json()["has_fulltext"] is False
    claim = next(x for x in c.get(f"/api/projects/{pid}").json()["claims"] if x["id"] == "c1")
    assert claim["status"] == "Reported, not independently checked"
    assert c.delete("/api/references/r1/fulltext").status_code == 400  # nothing left to remove


def test_exports_include_disclosure(client):
    c, db, _ = client
    pid = c.post("/api/projects", json={"title": "T", "question": "Does personalisation work?"}).json()["id"]
    _seed(db, pid)
    d = c.get(f"/api/projects/{pid}/disclosure").json()
    assert d["saved"] == "" and "No generative AI model was used" in d["text"]
    txt = c.get(f"/api/projects/{pid}/export", params={"fmt": "txt"}).text
    assert "AI-use disclosure" in txt and "A real study" in txt
    c.put(f"/api/projects/{pid}/disclosure", json={"text": "My own <b>wording</b>."})
    assert "My own <b>wording</b>." in c.get(f"/api/projects/{pid}/export", params={"fmt": "txt"}).text
    html = c.get(f"/api/projects/{pid}/export", params={"fmt": "html"}).text
    assert "My own &lt;b&gt;wording&lt;/b&gt;." in html  # escaped, not injected
    bib = c.get(f"/api/projects/{pid}/export", params={"fmt": "bib"}).text
    assert bib.startswith("% AI-use disclosure:") and "@article" in bib
    assert c.put(f"/api/projects/{pid}/disclosure", json={"text": ""}).json()["saved"] == ""
