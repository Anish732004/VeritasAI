"""End-to-end demo flow against the real OpenAlex and Crossref APIs.

Needs internet, so it only runs when asked:  VERITAS_LIVE=1 .venv/bin/python -m pytest -q tests/test_api_live.py
It uses a throwaway database and never touches data/veritas.db.
"""
import os
import tempfile

import pytest

pytestmark = pytest.mark.skipif(os.getenv("VERITAS_LIVE") != "1", reason="set VERITAS_LIVE=1 to run live API tests")


@pytest.fixture(scope="module")
def client():
    os.environ["VERITAS_DB"] = os.path.join(tempfile.mkdtemp(), "live.db")
    import importlib

    from backend import config
    importlib.reload(config)
    from backend import db
    importlib.reload(db)
    from fastapi.testclient import TestClient

    from backend.api import create_app
    return TestClient(create_app())


def test_full_demo_flow(client):
    c = client
    assert c.get("/api/status").json()["version"]
    pid = c.post("/api/projects", json={"title": "AI personalisation", "question":
             "Does AI-powered personalisation improve customer experience in ecommerce, and what risks or limitations have researchers identified?"}).json()["id"]

    # Checkpoint: no search before the plan is approved.
    assert c.post(f"/api/projects/{pid}/search").status_code == 409
    plan = c.post(f"/api/projects/{pid}/plan").json()
    assert plan["concept_groups"]
    assert c.post(f"/api/projects/{pid}/plan/approve").status_code == 200

    found = c.post(f"/api/projects/{pid}/search").json()
    assert found["results"], found["report"]
    top = found["results"][0]
    assert top["why"] and top["venue"]["tier"]

    saved = c.post(f"/api/projects/{pid}/references", json={"result": top}).json()
    assert saved["verification_status"] in ("Verified match", "Partial match"), saved.get("verification")
    assert c.post(f"/api/projects/{pid}/references", json={"result": top}).status_code == 409

    # Deliberately wrong title on a real DOI is caught as a mismatch.
    bad = c.post("/api/references", json={"project_id": pid, "title": "Deep learning for protein folding",
                                          "authors": "Shiu-Wan Hung", "year": "2021", "doi": "10.1016/j.jbusres.2020.11.022",
                                          "journal": "Journal of Business Research"}).json()
    assert bad["verification_status"] == "Mismatch"
    assert bad["verification"]["fields"]["title"]["status"] == "mismatch"

    # A made-up paper without DOI is not found.
    fake = c.post("/api/references", json={"project_id": pid, "title": "Quantum blockchain personalisation of lunar ecommerce shoppers",
                                           "authors": "Nobody Real", "year": "2023"}).json()
    assert fake["verification_status"] == "Not found"

    claim = c.post(f"/api/projects/{pid}/claims", json={"text": "AI personalisation improves customer satisfaction in online shopping."}).json()
    assert claim["status"] == "Not found"
    sugg = c.get(f"/api/claims/{claim['id']}/suggest", params={"reference_id": saved["id"]}).json()
    if sugg["suggestions"]:
        linked = c.post(f"/api/claims/{claim['id']}/evidence", json={"reference_id": saved["id"],
                        "passage": sugg["suggestions"][0]["text"], "origin": "suggested"}).json()
        assert linked["claim"]["status"] == "Source-supported"

    challenge = c.post(f"/api/claims/{claim['id']}/challenge").json()
    assert "results" in challenge and challenge["note"]

    # Export is gated on decisions.
    assert c.get(f"/api/projects/{pid}/export").status_code == 409
    c.post(f"/api/claims/{claim['id']}/decision", json={"decision": "Accepted", "reason": "reviewed"})
    c.post(f"/api/references/{saved['id']}/decision", json={"decision": "Accepted"})
    for r in (bad, fake):
        c.post(f"/api/references/{r['id']}/decision", json={"decision": "Rejected", "reason": "failed verification"})
    if saved["verification_status"] != "Verified match":
        c.post(f"/api/references/{saved['id']}/resolve", json={"action": "keep_mine", "reason": "checked the publisher page"})
    bib = c.get(f"/api/projects/{pid}/bibliography").json()
    assert bib["entries"] and not bib["blockers"], bib
    out = c.get(f"/api/projects/{pid}/export", params={"fmt": "txt"})
    assert out.status_code == 200 and "doi.org" in out.text

    summary = c.post(f"/api/projects/{pid}/summary").json()
    assert summary["sections"]
    events = c.get("/api/audit", params={"project": pid}).json()["events"]
    assert any(e["action"] == "Bibliography exported" for e in events)
