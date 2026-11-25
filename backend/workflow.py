"""Workflow orchestration: stage tracking, checkpoints and agent-run logging.

This is a small, explicit state machine rather than LangGraph: each agent is a plain
function with a narrow job, every run is persisted in `agent_runs` and the audit trail,
and the three human checkpoints from the blueprint are enforced by the API.
"""
from contextlib import contextmanager

from . import db

AGENTS = {
    "discovery": "Discovery Agent",
    "integrity": "Source Integrity Agent",
    "evidence": "Evidence Extraction Agent",
    "redteam": "Research Red Team",
    "academic": "Academic Integrity Agent",
}

STAGES = [
    ("define", "Define", "Enter a research question."),
    ("plan", "Plan", "Review the concept map and approve the plan."),
    ("discover", "Discover", "Search and save candidate sources."),
    ("verify", "Verify", "Review every source's verification result."),
    ("evidence", "Evidence", "Write claims and link source passages."),
    ("challenge", "Challenge", "Run the Red Team on your claims."),
    ("approve", "Approve", "Accept or reject each source and claim."),
    ("cite", "Cite", "Export the approved bibliography."),
]

VERIFIED_OK = "Verified match"


class Checkpoint(Exception):
    """Raised when an action is attempted before its human checkpoint is passed."""


@contextmanager
def agent_run(project_id: str | None, agent: str, payload: dict):
    run_id = db.new_id()
    with db.db() as con:
        db.insert(con, "agent_runs", {"id": run_id, "project_id": project_id, "agent": AGENTS[agent], "status": "running",
                                      "input": payload, "started_at": db.now()})
    box = {"summary": ""}
    try:
        yield box
    except Exception as e:
        with db.db() as con:
            db.update(con, "agent_runs", run_id, {"status": "failed", "error": str(e)[:500], "finished_at": db.now()})
        raise
    with db.db() as con:
        db.update(con, "agent_runs", run_id, {"status": "done", "output_summary": box["summary"][:500], "finished_at": db.now()})


def citable(ref: dict) -> bool:
    if ref.get("demo") or ref.get("decision") != "Accepted":
        return False
    return ref.get("verification_status") == VERIFIED_OK or bool(ref.get("override_reason"))


def verification_reviewed(ref: dict) -> bool:
    if ref.get("decision") == "Rejected":
        return True
    if not ref.get("verification_id"):
        return False
    return ref.get("verification_status") == VERIFIED_OK or bool(ref.get("override_reason"))


def stages(project: dict, refs: list[dict], claims: list[dict]) -> dict:
    real_refs = [r for r in refs if not r.get("demo")]
    active = [r for r in real_refs if r.get("decision") != "Rejected"]
    real_claims = [c for c in claims if not c.get("demo")]
    done = {
        "define": bool(project.get("question")),
        "plan": bool(project.get("plan_approved_at")),
        "discover": bool(active),
        "verify": bool(active) and all(verification_reviewed(r) for r in active),
        "evidence": any(c.get("status") in ("Source-supported", "Contradicted / qualified") for c in real_claims),
        "challenge": bool(project.get("challenged_at")),
        "approve": bool(real_claims) and bool(active)
                   and all(c.get("decision") != "Pending" for c in real_claims)
                   and all(r.get("decision") != "Pending" for r in real_refs)
                   and any(citable(r) for r in real_refs),
        "cite": bool(project.get("exported_at")),
    }
    todo = {
        "verify": [r["title"] for r in active if not verification_reviewed(r)][:5],
        "approve_claims": [c["text"] for c in real_claims if c.get("decision") == "Pending"][:5],
        "approve_refs": [r["title"] for r in real_refs if r.get("decision") == "Pending"][:5],
    }
    out, nxt = [], None
    for key, label, hint in STAGES:
        out.append({"key": key, "label": label, "done": done[key], "hint": hint})
        if not done[key] and nxt is None:
            nxt = {"key": key, "label": label, "hint": hint}
    return {"stages": out, "next": nxt, "todo": todo}


def export_gate(refs: list[dict], claims: list[dict]) -> list[str]:
    """Blueprint checkpoint: before export the student approves claims and references."""
    problems = []
    pending_claims = [c for c in claims if not c.get("demo") and c.get("decision") == "Pending"]
    pending_refs = [r for r in refs if not r.get("demo") and r.get("decision") == "Pending"]
    if pending_claims:
        problems.append(f"{len(pending_claims)} claim(s) still need your accept/reject decision.")
    if pending_refs:
        problems.append(f"{len(pending_refs)} source(s) still need your accept/reject decision.")
    if not any(citable(r) for r in refs):
        problems.append("No accepted source has verified (or reviewed) metadata yet.")
    return problems
