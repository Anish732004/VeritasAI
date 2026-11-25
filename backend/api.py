"""HTTP API. Every route is thin: it loads records, calls one agent, saves the result,
and writes an audit event. Network calls never run while a database write is open."""
import html
import json
import textwrap
from io import BytesIO

import httpx
from fastapi import APIRouter, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai, citations, concepts, db, evidence, governance, redteam, scholarly, search, verify, workflow
from .config import APP_VERSION, CONTACT_EMAIL, OPENAI_MODEL, OPENALEX_API_KEY, PROMPT_VERSION, ROOT, STATIC_DIR
from .db import audit, now
from .demo import seed_demo
from .text import strip_tags

api = APIRouter(prefix="/api")
MAX_PDF = 15 * 1024 * 1024


# ------------------------------------------------------------------ helpers

def _404(what="Record"):
    raise HTTPException(404, f"{what} not found")


def load_project(con, pid: str) -> dict:
    p = db.get(con, "projects", pid)
    if not p:
        _404("Project")
    return p


def load_refs(con, pid: str) -> list[dict]:
    return db.rows(con.execute("SELECT * FROM refs WHERE project_id = ? ORDER BY created_at", (pid,)))


def ref_public(con, r: dict, *, full: bool = False) -> dict:
    out = dict(r)
    out["has_fulltext"] = bool(r.get("fulltext"))
    if not full:
        out.pop("fulltext", None)
        out.pop("record", None)
    if r.get("verification_id"):
        out["verification"] = db.get(con, "verification_results", r["verification_id"])
    out["claim_count"] = con.execute(
        "SELECT COUNT(DISTINCT claim_id) FROM evidence_records WHERE reference_id = ?", (r["id"],)).fetchone()[0]
    return out


def claim_bundle(con, c: dict) -> dict:
    ev = db.rows(con.execute("SELECT * FROM evidence_records WHERE claim_id = ? ORDER BY created_at", (c["id"],)))
    out = dict(c)
    out["evidence"] = ev
    return out


def recompute_claim(con, claim_id: str) -> None:
    c = db.get(con, "claims", claim_id)
    if not c:
        return
    ev = db.rows(con.execute("SELECT * FROM evidence_records WHERE claim_id = ?", (claim_id,)))
    refs = {e["reference_id"]: db.get(con, "refs", e["reference_id"]) for e in ev}
    status, reason, level = evidence.claim_status(c, ev, refs)
    db.update(con, "claims", claim_id, {"status": status, "status_reason": reason, "evidence_level": level, "updated_at": now()})


def relocate_evidence_for_ref(con, ref_id: str) -> None:
    """Source text changed: re-check every passage that cites it, then refresh those claims."""
    ref = db.get(con, "refs", ref_id)
    claim_ids = set()
    for e in db.rows(con.execute("SELECT * FROM evidence_records WHERE reference_id = ?", (ref_id,))):
        if e.get("origin") == "red team":
            claim_ids.add(e["claim_id"])
            continue
        loc = evidence.locate(e["passage"], ref)
        db.update(con, "evidence_records", e["id"], {"match": loc["match"], "match_score": loc.get("score"),
                                                     "location": loc.get("location") or "",
                                                     "page": str(loc.get("page") or "")})
        claim_ids.add(e["claim_id"])
    for cid in claim_ids:
        recompute_claim(con, cid)


def project_bundle(con, pid: str) -> dict:
    p = load_project(con, pid)
    refs = [ref_public(con, r) for r in load_refs(con, pid)]
    claims = [claim_bundle(con, c) for c in db.rows(con.execute(
        "SELECT * FROM claims WHERE project_id = ? ORDER BY created_at", (pid,)))]
    flow = workflow.stages(p, refs, claims)
    for r in refs:
        r["citable"] = workflow.citable(r)
    return {"project": p, "references": refs, "claims": claims, "workflow": flow,
            "export_blockers": workflow.export_gate(refs, claims)}


def require_plan(p: dict) -> None:
    if not p.get("plan_approved_at"):
        raise HTTPException(409, "Checkpoint: approve the research plan first (blueprint: before broad searching).")


# ------------------------------------------------------------------ status & settings

@api.get("/status")
def status():
    with db.db() as con:
        demo = con.execute("SELECT COUNT(*) FROM projects WHERE demo = 1").fetchone()[0]
        name = db.setting(con, "name", "Researcher")
    return {"version": APP_VERSION, "ai": ai.available(), "model": OPENAI_MODEL if ai.available() else None,
            "ai_key": ai.configured(), "ai_enabled": ai.ENABLED,
            "openalex_key": bool(OPENALEX_API_KEY), "contact_email": bool(CONTACT_EMAIL), "demo_projects": demo,
            "name": name, "agents": list(workflow.AGENTS.values())}


class SettingsIn(BaseModel):
    name: str = Field(default="Researcher", max_length=80)


@api.put("/settings")
def save_settings(body: SettingsIn):
    with db.db() as con:
        db.set_setting(con, "name", body.name.strip() or "Researcher")
    return {"ok": True}


class AIToggleIn(BaseModel):
    enabled: bool


@api.put("/settings/ai")
def set_ai(body: AIToggleIn):
    """The student's informed choice to send data to the AI provider (governance policy)."""
    if body.enabled and not ai.configured():
        raise HTTPException(400, "Add OPENAI_API_KEY to .env and restart the server first.")
    with db.db() as con:
        db.set_setting(con, "ai_enabled", body.enabled)
        audit(con, "AI features turned " + ("on" if body.enabled else "off"),
              details="Student acknowledged what is sent to OpenAI." if body.enabled else "")
    ai.ENABLED = body.enabled
    return {"ok": True, "ai": ai.available()}


@api.get("/governance")
def get_governance():
    with db.db() as con:
        checks = governance.live_checks(con)
    return {"principles": governance.PRINCIPLES, "accountability": governance.ACCOUNTABILITY,
            "ai_may": governance.AI_MAY, "ai_may_not": governance.AI_MAY_NOT, "data": governance.DATA_POLICY,
            "risks": governance.RISKS, "guardrails": governance.GUARDRAILS, "checks": checks,
            "model_instructions": ai.GUARDRAILS, "prompt_version": PROMPT_VERSION}


# ------------------------------------------------------------------ overview

@api.get("/overview")
def overview():
    with db.db() as con:
        projects = db.rows(con.execute("SELECT * FROM projects ORDER BY created_at DESC"))
        out = []
        for p in projects:
            b = project_bundle(con, p["id"])
            real = [r for r in b["references"] if not r.get("demo")]
            claims = [c for c in b["claims"] if not c.get("demo")]
            out.append({**p, "workflow": b["workflow"],
                        "counts": {"references": len(real),
                                   "verified": sum(r["verification_status"] == "Verified match" for r in real),
                                   "needs_review": sum(not workflow.verification_reviewed(r) for r in real if r["decision"] != "Rejected"),
                                   "claims": len(claims),
                                   "supported": sum(c["status"] == "Source-supported" for c in claims),
                                   "linked": sum(c["status"] in ("Source-supported", "Contradicted / qualified", "AI interpretation") for c in claims),
                                   "unsupported": sum(c["status"] == "Not found" for c in claims),
                                   "accepted": sum(c["decision"] == "Accepted" for c in claims),
                                   "demo_items": len(b["references"]) - len(real) + len(b["claims"]) - len(claims)}})
        recent = db.rows(con.execute("SELECT * FROM audit_events ORDER BY created_at DESC LIMIT 6"))
        attention = db.rows(con.execute(
            "SELECT c.*, p.title AS project_title FROM claims c JOIN projects p ON p.id = c.project_id "
            "WHERE c.decision = 'Pending' AND c.demo = 0 ORDER BY c.updated_at DESC LIMIT 6"))
    return {"projects": out, "recent": recent, "attention": attention}


# ------------------------------------------------------------------ projects & plan

class ProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=5, max_length=2000)
    scope: str = Field(default="", max_length=2000)
    level: str = Field(default="", max_length=80)


@api.get("/projects")
def list_projects():
    with db.db() as con:
        return db.rows(con.execute("SELECT id, title, question, demo, plan_approved_at FROM projects ORDER BY created_at DESC"))


@api.post("/projects")
def create_project(body: ProjectIn):
    pid = db.new_id()
    with db.db() as con:
        db.insert(con, "projects", {"id": pid, "title": body.title.strip(), "question": body.question.strip(),
                                    "scope": body.scope.strip(), "level": body.level.strip(), "created_at": now()})
        audit(con, "Project created", project_id=pid, object_type="project", object_id=pid, details=body.title)
    return {"id": pid}


@api.get("/projects/{pid}")
def get_project(pid: str):
    with db.db() as con:
        b = project_bundle(con, pid)
        b["chat"] = db.rows(con.execute("SELECT * FROM chat WHERE project_id = ? ORDER BY created_at DESC LIMIT 6", (pid,)))
        return b


class ProjectPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    question: str | None = Field(default=None, max_length=2000)
    scope: str | None = Field(default=None, max_length=2000)
    level: str | None = Field(default=None, max_length=80)


@api.patch("/projects/{pid}")
def patch_project(pid: str, body: ProjectPatch):
    data = {k: v.strip() for k, v in body.model_dump().items() if v is not None}
    with db.db() as con:
        p = load_project(con, pid)
        if "question" in data and data["question"] != p["question"]:
            data["plan_approved_at"] = None
        db.update(con, "projects", pid, data)
        audit(con, "Project edited", project_id=pid, object_type="project", object_id=pid, details=", ".join(data))
    return {"ok": True}


@api.delete("/projects/{pid}")
def delete_project(pid: str):
    with db.db() as con:
        p = load_project(con, pid)
        con.execute("DELETE FROM projects WHERE id = ?", (pid,))
        audit(con, "Project deleted", object_type="project", object_id=pid, details=p["title"])
    return {"ok": True}


@api.post("/projects/{pid}/plan")
def generate_plan(pid: str):
    with db.db() as con:
        p = load_project(con, pid)
    meta = None
    with workflow.agent_run(pid, "discovery", {"question": p["question"]}) as run:
        plan = None
        if ai.available():
            try:
                plan, meta = concepts.ai_plan(p["question"], p.get("scope") or "", p.get("level") or "")
            except ai.AIUnavailable as e:
                plan = concepts.template_plan(p["question"])
                plan["generated_by"] += f" — AI unavailable: {e}"
        if plan is None:
            plan = concepts.template_plan(p["question"])
        run["summary"] = f"{len(plan['concept_groups'])} concept groups"
    with db.db() as con:
        db.update(con, "projects", pid, {"plan": plan, "plan_approved_at": None})
        audit(con, "Plan proposed", actor="Discovery Agent", project_id=pid, object_type="project", object_id=pid,
              details=plan["generated_by"], ai=meta)
    return plan


class PlanIn(BaseModel):
    themes: list[str] = []
    subquestions: list[str] = []
    inclusion_criteria: list[str] = []
    concept_groups: list[dict]
    filters: dict = {}


@api.put("/projects/{pid}/plan")
def save_plan(pid: str, body: PlanIn):
    groups = concepts.clean_groups(body.concept_groups)
    if not groups:
        raise HTTPException(400, "The plan needs at least one concept group with search terms.")
    if not any(g["required"] for g in groups):
        groups[0]["required"] = True
    f = {**concepts.default_filters(), **{k: v for k, v in body.filters.items() if k in concepts.default_filters()}}
    with db.db() as con:
        p = load_project(con, pid)
        plan = {**(p.get("plan") or {}), "themes": body.themes[:8], "subquestions": body.subquestions[:8],
                "inclusion_criteria": body.inclusion_criteria[:8], "concept_groups": groups, "filters": f}
        plan.setdefault("generated_by", "Written by student")
        db.update(con, "projects", pid, {"plan": plan})
    return plan


@api.post("/projects/{pid}/plan/approve")
def approve_plan(pid: str):
    with db.db() as con:
        p = load_project(con, pid)
        if not (p.get("plan") or {}).get("concept_groups"):
            raise HTTPException(400, "Generate or write a plan first.")
        db.update(con, "projects", pid, {"plan_approved_at": now()})
        db.decision(con, "plan", pid, "Approved")
        audit(con, "Plan approved", project_id=pid, object_type="project", object_id=pid,
              details="; ".join(g["label"] + (" (required)" if g["required"] else "") for g in p["plan"]["concept_groups"]))
    return {"ok": True}


@api.post("/projects/{pid}/plan/reopen")
def reopen_plan(pid: str):
    with db.db() as con:
        load_project(con, pid)
        db.update(con, "projects", pid, {"plan_approved_at": None})
        audit(con, "Plan reopened for editing", project_id=pid, object_type="project", object_id=pid)
    return {"ok": True}


# ------------------------------------------------------------------ discovery

@api.post("/projects/{pid}/search")
def run_search(pid: str):
    with db.db() as con:
        p = load_project(con, pid)
        require_plan(p)
        existing = load_refs(con, pid)
    dois = {r["doi"] for r in existing if r.get("doi")}
    titles = {r["title"].lower() for r in existing}
    with workflow.agent_run(pid, "discovery", {"groups": [g["label"] for g in p["plan"]["concept_groups"]]}) as run:
        try:
            out = search.discover(p["plan"], dois, titles)
        except scholarly.ServiceError as e:
            raise HTTPException(502, f"{e}. No results were invented; retry in a moment.")
        except ValueError as e:
            raise HTTPException(400, str(e))
        run["summary"] = f"{out['report']['retrieved']} retrieved, {out['report']['shown']} shown"
    with db.db() as con:
        audit(con, "Literature search", actor="Discovery Agent", project_id=pid, object_type="project", object_id=pid,
              details=f"{out['report']['retrieved']} retrieved · {out['report']['shown']} shown · removed {out['report']['removed']}")
    return out


class SaveResultIn(BaseModel):
    result: dict


def _ref_from_result(pid: str, r: dict) -> dict:
    return {
        "id": db.new_id(), "project_id": pid, "title": strip_tags(r.get("title", ""))[:500],
        "authors": [{"given": a.get("given", ""), "family": a.get("family", "")} for a in r.get("authors") or []][:100],
        "year": str(r.get("year") or ""), "doi": scholarly.clean_doi(r.get("doi", "")), "journal": r.get("journal", ""),
        "issn": r.get("issn") or [], "volume": r.get("volume", ""), "issue": r.get("issue", ""), "pages": r.get("pages", ""),
        "url": r.get("url", ""), "abstract": r.get("abstract", "")[:20000], "metadata_source": r.get("provider", "OpenAlex"),
        "external_id": r.get("external_id", ""), "retrieved_at": now(),
        "kind": scholarly.work_kind(r.get("type", ""), r.get("source_type", "")) if r.get("kind") is None else r["kind"],
        "discovery": {"score": r.get("score"), "why": r.get("why"), "concepts": r.get("concepts"),
                      "foundational": bool(r.get("foundational")), "oa_url": r.get("oa_url", ""),
                      "sentence": r.get("sentence")},
        "venue": r.get("venue"), "created_at": now(), "updated_at": now(),
    }


def _verify_and_store(ref_id: str, project_id: str | None) -> dict:
    with db.db() as con:
        ref = db.get(con, "refs", ref_id)
    if not ref:
        _404("Reference")
    if ref.get("demo"):
        raise HTTPException(400, "Demo sources are synthetic and can never be verified.")
    with workflow.agent_run(project_id, "integrity", {"reference_id": ref_id}) as run:
        result = verify.run(ref)
        run["summary"] = result["status"]
    vid = db.new_id()
    with db.db() as con:
        db.insert(con, "verification_results", {
            "id": vid, "reference_id": ref_id, "status": result["status"], "reason": result["reason"],
            "fields": result["fields"],
            "matched_fields": [k for k, v in result["fields"].items() if v["status"] == "match"],
            "discrepancies": {k: v for k, v in result["fields"].items() if v["status"] in ("mismatch", "partial")},
            "searched": result["searched"], "record": result["record"], "suggestions": result["suggestions"],
            "checked_at": now()})
        db.update(con, "refs", ref_id, {"verification_status": result["status"], "verification_id": vid,
                                        "updated_at": now(),
                                        "override_reason": "" if result["status"] == verify.STATUS_VERIFIED else ref.get("override_reason", "")})
        audit(con, f"Metadata check: {result['status']}", actor="Source Integrity Agent", project_id=ref["project_id"],
              object_type="reference", object_id=ref_id, details=f"{ref['title'][:120]} — {result['reason'][:300]}")
        return ref_public(con, db.get(con, "refs", ref_id))


@api.post("/projects/{pid}/references")
def save_result(pid: str, body: SaveResultIn):
    with db.db() as con:
        p = load_project(con, pid)
        require_plan(p)
        data = _ref_from_result(pid, body.result)
        if not data["title"]:
            raise HTTPException(400, "Result has no title.")
        dup = con.execute("SELECT id FROM refs WHERE project_id = ? AND ((doi != '' AND doi = ?) OR lower(title) = lower(?))",
                          (pid, data["doi"], data["title"])).fetchone()
        if dup:
            raise HTTPException(409, "Already saved in this project.")
        data["original"] = {k: data[k] for k in ("title", "authors", "year", "doi", "journal", "volume", "issue", "pages")}
        db.insert(con, "refs", data)
        audit(con, "Source saved", project_id=pid, object_type="reference", object_id=data["id"], details=data["title"][:200])
    # Verification runs straight away so the status is visible beside the source.
    try:
        return _verify_and_store(data["id"], pid)
    except HTTPException:
        raise
    except Exception as e:  # never block saving on a verification failure
        with db.db() as con:
            return ref_public(con, db.get(con, "refs", data["id"])) | {"verify_error": str(e)}


class ManualRefIn(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=500)
    authors: str = Field(default="", max_length=3000)
    year: str = Field(default="", max_length=10)
    doi: str = Field(default="", max_length=200)
    journal: str = Field(default="", max_length=300)
    volume: str = Field(default="", max_length=30)
    issue: str = Field(default="", max_length=30)
    pages: str = Field(default="", max_length=30)
    url: str = Field(default="", max_length=500)
    abstract: str = Field(default="", max_length=20000)
    folder: str = Field(default="", max_length=100)
    tags: list[str] = []
    notes: str = Field(default="", max_length=10000)


def parse_authors(text: str) -> list[dict]:
    return [scholarly.split_name(n) for n in text.split(";") if n.strip()]


@api.post("/references")
def add_manual_reference(body: ManualRefIn):
    with db.db() as con:
        load_project(con, body.project_id)
        rid = db.new_id()
        data = {"id": rid, "project_id": body.project_id, "title": body.title.strip(), "authors": parse_authors(body.authors),
                "year": body.year.strip(), "doi": scholarly.clean_doi(body.doi), "journal": body.journal.strip(),
                "volume": body.volume.strip(), "issue": body.issue.strip(), "pages": body.pages.strip(), "url": body.url.strip(),
                "abstract": body.abstract.strip(), "folder": body.folder.strip(), "tags": [t.strip() for t in body.tags if t.strip()][:20],
                "notes": body.notes, "metadata_source": "Entered by student", "created_at": now(), "updated_at": now()}
        data["original"] = {k: data[k] for k in ("title", "authors", "year", "doi", "journal", "volume", "issue", "pages")}
        db.insert(con, "refs", data)
        audit(con, "Reference added manually", project_id=body.project_id, object_type="reference", object_id=rid, details=data["title"][:200])
    try:
        return _verify_and_store(rid, body.project_id)
    except Exception as e:
        with db.db() as con:
            return ref_public(con, db.get(con, "refs", rid)) | {"verify_error": str(e)}


@api.get("/references")
def list_references(project: str = "", q: str = "", status: str = "", tag: str = "", folder: str = ""):
    sql, args = "SELECT r.*, p.title AS project_title FROM refs r JOIN projects p ON p.id = r.project_id WHERE 1=1", []
    if project:
        sql += " AND r.project_id = ?"; args.append(project)
    if status:
        sql += " AND r.verification_status = ?"; args.append(status)
    if folder:
        sql += " AND r.folder = ?"; args.append(folder)
    if q:
        sql += " AND (lower(r.title) LIKE ? OR lower(r.authors) LIKE ? OR lower(r.doi) LIKE ? OR lower(r.notes) LIKE ? OR lower(r.tags) LIKE ?)"
        args += [f"%{q.lower()}%"] * 5
    sql += " ORDER BY r.created_at DESC"
    with db.db() as con:
        refs = [ref_public(con, r) for r in db.rows(con.execute(sql, args))]
    if tag:
        refs = [r for r in refs if tag in (r.get("tags") or [])]
    # Duplicate alerts across projects (same DOI or same normalised title).
    seen = {}
    for r in refs:
        k = r.get("doi") or "".join(ch for ch in r["title"].lower() if ch.isalnum())
        seen.setdefault(k, []).append(r["id"])
    for r in refs:
        k = r.get("doi") or "".join(ch for ch in r["title"].lower() if ch.isalnum())
        r["duplicates"] = [x for x in seen[k] if x != r["id"]]
    return refs


@api.get("/references/{rid}")
def get_reference(rid: str):
    with db.db() as con:
        r = db.get(con, "refs", rid)
        if not r:
            _404("Reference")
        out = ref_public(con, r, full=True)
        out["fulltext_preview"] = (r.get("fulltext") or "")[:3000]
        out.pop("fulltext", None)
        out["claims"] = db.rows(con.execute(
            "SELECT DISTINCT c.id, c.text, c.status, e.stance FROM evidence_records e JOIN claims c ON c.id = e.claim_id WHERE e.reference_id = ?", (rid,)))
        out["history"] = db.rows(con.execute(
            "SELECT id, status, reason, checked_at FROM verification_results WHERE reference_id = ? ORDER BY checked_at DESC", (rid,)))
        return out


class RefPatch(BaseModel):
    title: str | None = None
    authors: str | None = None
    year: str | None = None
    doi: str | None = None
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    url: str | None = None
    folder: str | None = None
    tags: list[str] | None = None
    notes: str | None = None


METADATA_FIELDS = {"title", "authors", "year", "doi", "journal", "volume", "issue", "pages"}


@api.patch("/references/{rid}")
def patch_reference(rid: str, body: RefPatch):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    if "authors" in data:
        data["authors"] = parse_authors(data["authors"])
    if "doi" in data:
        data["doi"] = scholarly.clean_doi(data["doi"])
    if "tags" in data:
        data["tags"] = [t.strip() for t in data["tags"] if t.strip()][:20]
    with db.db() as con:
        r = db.get(con, "refs", rid)
        if not r:
            _404("Reference")
        if "title" in data and not data["title"].strip():
            raise HTTPException(400, "A title is required.")
        changed_meta = [k for k in METADATA_FIELDS & data.keys() if data[k] != r.get(k)]
        if changed_meta:
            data.update({"verification_status": "Pending review", "override_reason": ""})
        data["updated_at"] = now()
        db.update(con, "refs", rid, data)
        audit(con, "Source edited", project_id=r["project_id"], object_type="reference", object_id=rid,
              details=(f"Metadata changed ({', '.join(changed_meta)}); re-check needed. " if changed_meta else "") + r["title"][:150])
    if changed_meta and not r.get("demo"):
        return _verify_and_store(rid, r["project_id"])
    with db.db() as con:
        return ref_public(con, db.get(con, "refs", rid))


@api.delete("/references/{rid}")
def delete_reference(rid: str):
    with db.db() as con:
        r = db.get(con, "refs", rid)
        if not r:
            _404("Reference")
        claim_ids = [x[0] for x in con.execute("SELECT DISTINCT claim_id FROM evidence_records WHERE reference_id = ?", (rid,))]
        con.execute("DELETE FROM refs WHERE id = ?", (rid,))
        for cid in claim_ids:
            recompute_claim(con, cid)
        audit(con, "Source deleted", project_id=r["project_id"], object_type="reference", object_id=rid, details=r["title"][:200])
    return {"ok": True, "claims_affected": len(claim_ids)}


@api.post("/references/{rid}/verify")
def verify_reference(rid: str):
    with db.db() as con:
        r = db.get(con, "refs", rid)
    if not r:
        _404("Reference")
    return _verify_and_store(rid, r["project_id"])


class ResolveIn(BaseModel):
    action: str  # accept_database | keep_mine
    reason: str = Field(default="", max_length=1000)
    fields: list[str] | None = None


@api.post("/references/{rid}/resolve")
def resolve_reference(rid: str, body: ResolveIn):
    with db.db() as con:
        r = db.get(con, "refs", rid)
        if not r:
            _404("Reference")
        v = db.get(con, "verification_results", r["verification_id"]) if r.get("verification_id") else None
        if body.action == "keep_mine":
            if not body.reason.strip():
                raise HTTPException(400, "Give a reason for keeping your values; it is recorded in the audit trail.")
            db.update(con, "refs", rid, {"override_reason": body.reason.strip(), "updated_at": now()})
            db.decision(con, "reference_metadata", rid, "Kept student values", body.reason.strip())
            audit(con, "Kept own metadata despite check", project_id=r["project_id"], object_type="reference",
                  object_id=rid, details=f"{r['title'][:120]} — {body.reason.strip()}")
            return ref_public(con, db.get(con, "refs", rid))
        if body.action != "accept_database" or not v:
            raise HTTPException(400, "Nothing to accept; run a check first.")
        sugg = v.get("suggestions") or {}
        fields = [f for f in (body.fields or list(sugg)) if f in sugg]
        if not fields:
            raise HTTPException(400, "The database record offers no different values.")
        update = {f: sugg[f] for f in fields}
        if "doi" in update:
            update["doi"] = scholarly.clean_doi(update["doi"])
        update["updated_at"] = now()
        db.update(con, "refs", rid, update)
        db.decision(con, "reference_metadata", rid, "Accepted database values", ", ".join(fields))
        audit(con, "Accepted database metadata", project_id=r["project_id"], object_type="reference", object_id=rid,
              details=f"Fields: {', '.join(fields)}. Original values kept in the record history.")
    return _verify_and_store(rid, r["project_id"])


class DecisionIn(BaseModel):
    decision: str
    reason: str = Field(default="", max_length=1000)


@api.post("/references/{rid}/decision")
def decide_reference(rid: str, body: DecisionIn):
    if body.decision not in ("Accepted", "Rejected", "Pending"):
        raise HTTPException(400, "Decision must be Accepted, Rejected or Pending.")
    with db.db() as con:
        r = db.get(con, "refs", rid)
        if not r:
            _404("Reference")
        if r.get("demo") and body.decision == "Accepted":
            raise HTTPException(400, "Demo sources cannot be accepted for citation.")
        db.update(con, "refs", rid, {"decision": body.decision, "decision_reason": body.reason, "updated_at": now()})
        db.decision(con, "reference", rid, body.decision, body.reason)
        audit(con, f"Source {body.decision.lower()}", project_id=r["project_id"], object_type="reference", object_id=rid,
              details=r["title"][:150] + (f" — {body.reason}" if body.reason else ""))
        return ref_public(con, db.get(con, "refs", rid))


# ------------------------------------------------------------------ full text

def _store_fulltext(rid: str, text: str, origin: str) -> dict:
    with db.db() as con:
        r = db.get(con, "refs", rid)
        if not r:
            _404("Reference")
        db.update(con, "refs", rid, {"fulltext": text[:600000], "fulltext_origin": origin, "updated_at": now()})
        relocate_evidence_for_ref(con, rid)
        audit(con, "Full text attached", actor="Evidence Extraction Agent", project_id=r["project_id"],
              object_type="reference", object_id=rid, details=f"{origin}; {len(text):,} characters")
        return ref_public(con, db.get(con, "refs", rid))


@api.delete("/references/{rid}/fulltext")
def remove_fulltext(rid: str):
    """Data-retention control: forget the stored full text; linked passages are re-checked."""
    with db.db() as con:
        r = db.get(con, "refs", rid)
        if not r:
            _404("Reference")
        if not r.get("fulltext"):
            raise HTTPException(400, "No full text is stored for this source.")
        db.update(con, "refs", rid, {"fulltext": "", "fulltext_origin": "", "updated_at": now()})
        relocate_evidence_for_ref(con, rid)
        audit(con, "Stored full text removed", project_id=r["project_id"], object_type="reference", object_id=rid,
              details=r["title"][:150])
        return ref_public(con, db.get(con, "refs", rid))


def pdf_to_text(raw: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(raw))
    pages = [f"[PDF page {i + 1}]\n" + (p.extract_text() or "") for i, p in enumerate(reader.pages[:300])]
    text = "\n\n".join(pages)
    if len(text.replace("[PDF page", "").strip()) < 200:
        raise HTTPException(422, "No extractable text: this looks like a scanned PDF (OCR is not supported).")
    return text


@api.post("/references/{rid}/fulltext/pdf")
async def upload_pdf(rid: str, file: UploadFile = File(...)):
    raw = await file.read(MAX_PDF + 1)
    if len(raw) > MAX_PDF or not raw.startswith(b"%PDF"):
        raise HTTPException(400, "Upload a PDF of at most 15 MB.")
    try:
        text = pdf_to_text(raw)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Unable to read this PDF.")
    return _store_fulltext(rid, text, f"Uploaded PDF ({strip_tags(file.filename or 'file')[:80]})")


class TextIn(BaseModel):
    text: str = Field(min_length=50, max_length=600000)


@api.post("/references/{rid}/fulltext/text")
def paste_text(rid: str, body: TextIn):
    return _store_fulltext(rid, body.text, "Pasted by student")


@api.post("/references/{rid}/fulltext/open-access")
def fetch_open_access(rid: str):
    with db.db() as con:
        r = db.get(con, "refs", rid)
    if not r:
        _404("Reference")
    url = ((r.get("discovery") or {}).get("oa_url") if isinstance(r.get("discovery"), dict) else "") or ""
    if not url and r.get("doi"):
        try:
            url = scholarly.openalex_by_doi(r["doi"]).get("oa_url", "")
        except (scholarly.NotFound, scholarly.ServiceError):
            url = ""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(404, "OpenAlex lists no open-access copy for this work. Upload a PDF you are permitted to use.")
    try:
        with httpx.stream("GET", url, timeout=30, follow_redirects=True,
                          headers={"User-Agent": scholarly.USER_AGENT}) as resp:
            chunks, size = [], 0
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > MAX_PDF:
                    raise HTTPException(413, "Open-access file is larger than 15 MB.")
                chunks.append(chunk)
        raw = b"".join(chunks)
    except httpx.HTTPError:
        raise HTTPException(502, "Could not download the open-access copy. Open the link and upload the PDF instead.")
    if not raw.startswith(b"%PDF"):
        raise HTTPException(422, f"The open-access link is a web page, not a PDF. Open it, download the PDF and upload it: {url}")
    return _store_fulltext(rid, pdf_to_text(raw), f"Open-access PDF from {httpx.URL(url).host}")


# ------------------------------------------------------------------ claims & evidence

class ClaimIn(BaseModel):
    text: str = Field(min_length=5, max_length=2000)
    claim_type: str = "source_finding"


@api.post("/projects/{pid}/claims")
def create_claim(pid: str, body: ClaimIn):
    if body.claim_type not in ("source_finding", "ai_interpretation"):
        raise HTTPException(400, "Unknown claim type.")
    with db.db() as con:
        p = load_project(con, pid)
        require_plan(p)
        cid = db.new_id()
        db.insert(con, "claims", {"id": cid, "project_id": pid, "text": body.text.strip(), "claim_type": body.claim_type,
                                  "created_at": now(), "updated_at": now()})
        recompute_claim(con, cid)
        audit(con, "Claim created", project_id=pid, object_type="claim", object_id=cid, details=body.text[:200])
        return claim_bundle(con, db.get(con, "claims", cid))


class ClaimPatch(BaseModel):
    text: str | None = Field(default=None, max_length=2000)
    claim_type: str | None = None


@api.patch("/claims/{cid}")
def patch_claim(cid: str, body: ClaimPatch):
    with db.db() as con:
        c = db.get(con, "claims", cid)
        if not c:
            _404("Claim")
        data = {k: v for k, v in body.model_dump().items() if v is not None}
        if data.get("claim_type") not in (None, "source_finding", "ai_interpretation"):
            raise HTTPException(400, "Unknown claim type.")
        data.update({"decision": "Pending", "updated_at": now()})
        db.update(con, "claims", cid, data)
        recompute_claim(con, cid)
        audit(con, "Claim edited (decision reset to pending)", project_id=c["project_id"], object_type="claim", object_id=cid,
              details=(data.get("text") or c["text"])[:200])
        return claim_bundle(con, db.get(con, "claims", cid))


@api.delete("/claims/{cid}")
def delete_claim(cid: str):
    with db.db() as con:
        c = db.get(con, "claims", cid)
        if not c:
            _404("Claim")
        con.execute("DELETE FROM claims WHERE id = ?", (cid,))
        audit(con, "Claim deleted", project_id=c["project_id"], object_type="claim", object_id=cid, details=c["text"][:200])
    return {"ok": True}


@api.post("/claims/{cid}/decision")
def decide_claim(cid: str, body: DecisionIn):
    if body.decision not in ("Accepted", "Rejected", "Pending"):
        raise HTTPException(400, "Decision must be Accepted, Rejected or Pending.")
    with db.db() as con:
        c = db.get(con, "claims", cid)
        if not c:
            _404("Claim")
        if c["status"] == evidence.NOT_FOUND and body.decision == "Accepted" and not body.reason.strip():
            raise HTTPException(400, "This claim has no located evidence. Give a reason to accept it anyway, or relabel it as interpretation.")
        db.update(con, "claims", cid, {"decision": body.decision, "decision_reason": body.reason, "updated_at": now()})
        db.decision(con, "claim", cid, body.decision, body.reason)
        audit(con, f"Claim {body.decision.lower()}", project_id=c["project_id"], object_type="claim", object_id=cid,
              details=c["text"][:150] + (f" — {body.reason}" if body.reason else ""))
        return claim_bundle(con, db.get(con, "claims", cid))


@api.get("/claims/{cid}/suggest")
def suggest_passages(cid: str, reference_id: str):
    with db.db() as con:
        c = db.get(con, "claims", cid)
        r = db.get(con, "refs", reference_id)
        if not c or not r:
            _404()
    with workflow.agent_run(c["project_id"], "evidence", {"claim_id": cid, "reference_id": reference_id}) as run:
        sugg = evidence.suggest(c["text"], r)
        run["summary"] = f"{len(sugg)} candidate passages"
    available = [x for x, _ in evidence.source_texts(r)]
    return {"suggestions": sugg, "available": available,
            "note": ("Only the abstract is stored; suggestions are abstract-level." if available == ["abstract"] else
                     "No source text stored. Attach the PDF or paste permitted text to get suggestions." if not available else
                     "Suggestions are sentences copied from the stored text, ranked by shared wording; you decide if one supports the claim.")}


class EvidenceIn(BaseModel):
    reference_id: str
    passage: str = Field(min_length=10, max_length=5000)
    stance: str = "supports"
    origin: str = "student"


@api.post("/claims/{cid}/evidence")
def add_evidence(cid: str, body: EvidenceIn):
    if body.stance not in ("supports", "qualifies", "challenges"):
        raise HTTPException(400, "Unknown stance.")
    with db.db() as con:
        c = db.get(con, "claims", cid)
        r = db.get(con, "refs", body.reference_id)
        if not c or not r:
            _404()
        loc = evidence.locate(body.passage, r)
        eid = db.new_id()
        db.insert(con, "evidence_records", {
            "id": eid, "claim_id": cid, "reference_id": r["id"], "passage": body.passage.strip(),
            "location": loc.get("location") or "", "page": str(loc.get("page") or ""), "match": loc["match"],
            "match_score": loc.get("score"), "stance": body.stance,
            "origin": body.origin if body.origin in ("student", "suggested") else "student", "created_at": now()})
        recompute_claim(con, cid)
        audit(con, "Evidence linked", actor="Evidence Extraction Agent" if body.origin == "suggested" else "Student",
              project_id=c["project_id"], object_type="claim", object_id=cid,
              details=f"{body.stance} · {loc['match']} · {r['title'][:100]}")
        return {"claim": claim_bundle(con, db.get(con, "claims", cid)), "match": loc}


@api.delete("/evidence/{eid}")
def delete_evidence(eid: str):
    with db.db() as con:
        e = db.get(con, "evidence_records", eid)
        if not e:
            _404("Evidence record")
        con.execute("DELETE FROM evidence_records WHERE id = ?", (eid,))
        recompute_claim(con, e["claim_id"])
        c = db.get(con, "claims", e["claim_id"])
        audit(con, "Evidence unlinked", project_id=c["project_id"], object_type="claim", object_id=c["id"], details=e["passage"][:150])
    return {"ok": True}


# ------------------------------------------------------------------ red team

@api.get("/projects/{pid}/redteam")
def redteam_alerts(pid: str):
    with db.db() as con:
        load_project(con, pid)
        claims = db.rows(con.execute("SELECT * FROM claims WHERE project_id = ? AND demo = 0", (pid,)))
        out = []
        for c in claims:
            ev = db.rows(con.execute("SELECT * FROM evidence_records WHERE claim_id = ?", (c["id"],)))
            refs = {e["reference_id"]: db.get(con, "refs", e["reference_id"]) for e in ev}
            out.append({"claim": claim_bundle(con, c), "alerts": redteam.rule_checks(c, ev, refs)})
    return out


@api.post("/claims/{cid}/challenge")
def challenge_claim(cid: str):
    with db.db() as con:
        c = db.get(con, "claims", cid)
        if not c:
            _404("Claim")
        ev = db.rows(con.execute("SELECT * FROM evidence_records WHERE claim_id = ?", (cid,)))
        refs = {e["reference_id"]: db.get(con, "refs", e["reference_id"]) for e in ev}
        project_dois = {r["doi"] for r in db.rows(con.execute("SELECT doi FROM refs WHERE project_id = ?", (c["project_id"],))) if r["doi"]}
    with workflow.agent_run(c["project_id"], "redteam", {"claim_id": cid}) as run:
        try:
            found = redteam.search_counter_evidence(c, {r.get("doi") for r in refs.values() if r} - {""})
        except scholarly.ServiceError as e:
            raise HTTPException(502, f"{e}. Counter-evidence search incomplete; nothing was invented.")
        except ValueError as e:
            raise HTTPException(400, str(e))
        questions, qmeta = [], None
        if ai.available():
            try:
                questions, qmeta = redteam.challenge_questions(c, "\n".join(e["passage"] for e in ev))
            except ai.AIUnavailable:
                pass
        run["summary"] = f"{len(found['results'])} candidate counter-sources"
    for r in found["results"]:
        r["in_project"] = bool(r.get("doi") and r["doi"] in project_dois)
    with db.db() as con:
        db.update(con, "projects", c["project_id"], {"challenged_at": now()})
        audit(con, "Red Team challenge", actor="Research Red Team", project_id=c["project_id"], object_type="claim",
              object_id=cid, details=f"{len(found['results'])} candidate counter-sources · {c['text'][:120]}",
              ai=found.get("ai") or qmeta)
    return {**found, "alerts": redteam.rule_checks(c, ev, refs), "questions": questions,
            "questions_label": f"AI-generated questions ({qmeta['model']}), unverified" if qmeta else None}


class CounterIn(BaseModel):
    result: dict
    sentence: str = Field(min_length=10, max_length=3000)
    stance: str


@api.post("/claims/{cid}/counter")
def link_counter(cid: str, body: CounterIn):
    if body.stance not in ("supports", "qualifies", "challenges"):
        raise HTTPException(400, "Choose supports, qualifies or challenges.")
    with db.db() as con:
        c = db.get(con, "claims", cid)
        if not c:
            _404("Claim")
        data = _ref_from_result(c["project_id"], body.result)
        existing = con.execute("SELECT id FROM refs WHERE project_id = ? AND ((doi != '' AND doi = ?) OR lower(title) = lower(?))",
                               (c["project_id"], data["doi"], data["title"])).fetchone()
        if existing:
            rid = existing[0]
            new = False
        else:
            data["original"] = {k: data[k] for k in ("title", "authors", "year", "doi", "journal", "volume", "issue", "pages")}
            data["folder"] = "Counter-evidence"
            db.insert(con, "refs", data)
            rid, new = data["id"], True
        ref = db.get(con, "refs", rid)
        loc = evidence.locate(body.sentence, ref)
        db.insert(con, "evidence_records", {
            "id": db.new_id(), "claim_id": cid, "reference_id": rid, "passage": body.sentence, "location": loc.get("location") or "abstract",
            "page": "", "match": loc["match"], "match_score": loc.get("score"), "stance": body.stance,
            "stance_method": "student confirmed", "origin": "red team", "created_at": now()})
        recompute_claim(con, cid)
        audit(con, f"Counter-evidence linked ({body.stance})", project_id=c["project_id"], object_type="claim", object_id=cid,
              details=f"{data['title'][:120]}")
    if new:
        try:
            _verify_and_store(rid, c["project_id"])
        except Exception:
            pass
    with db.db() as con:
        return claim_bundle(con, db.get(con, "claims", cid))


# ------------------------------------------------------------------ summary & assistant

def _author_year(r: dict) -> str:
    fams = [a.get("family") or a.get("name", "") for a in r.get("authors") or []]
    who = fams[0] + (" et al." if len(fams) > 2 else f" & {fams[1]}" if len(fams) == 2 else "") if fams else "Unknown"
    return f"{who}, {r.get('year') or 'n.d.'}"


@api.post("/projects/{pid}/summary")
def build_summary(pid: str):
    with db.db() as con:
        b = project_bundle(con, pid)
    refs = {r["id"]: r for r in b["references"]}
    claims = [c for c in b["claims"] if c["decision"] != "Rejected"]
    if not claims:
        raise HTTPException(400, "Write at least one claim before building a summary.")
    sections = {}
    for c in claims:
        support = [e for e in c["evidence"] if e["stance"] == "supports" and e["match"] in ("exact", "near")]
        counter = [e for e in c["evidence"] if e["stance"] in ("qualifies", "challenges")]
        item = {"claim_id": c["id"], "text": c["text"], "status": c["status"], "reason": c["status_reason"],
                "decision": c["decision"],
                "citations": [{"ref": _author_year(refs[e["reference_id"]]), "reference_id": e["reference_id"],
                               "passage": e["passage"], "location": e["location"], "evidence_id": e["id"]}
                              for e in support if e["reference_id"] in refs],
                "counter": [{"ref": _author_year(refs[e["reference_id"]]), "passage": e["passage"], "stance": e["stance"]}
                            for e in counter if e["reference_id"] in refs]}
        sections.setdefault(c["status"], []).append(item)
    order = [evidence.SOURCE_SUPPORTED, evidence.CONTRADICTED, evidence.REPORTED, evidence.AI_INTERPRETATION,
             evidence.NOT_FOUND, evidence.DEMO]
    summary = {"generated_at": now(), "sections": [{"status": s, "items": sections[s]} for s in order if s in sections],
               "synthesis": None}
    if ai.available():
        supported = [{"claim_id": i["claim_id"], "claim": i["text"], "status": s["status"],
                      "passages": [x["passage"] for x in i["citations"]][:3]}
                     for s in summary["sections"] if s["status"] in (evidence.SOURCE_SUPPORTED, evidence.CONTRADICTED)
                     for i in s["items"]]
        if supported:
            try:
                data, meta = ai.complete_json(
                    "Write a short evidence-backed synthesis (3-6 sentences) of the research question using ONLY the "
                    "claims provided. Return a list of objects {sentence, claim_ids}. Use claim_ids for every sentence "
                    "that restates a claim; leave claim_ids empty for your own connecting reasoning.",
                    "Research question: " + b["project"]["question"], data=json.dumps(supported)[:12000],
                    inputs=[x["claim_id"] for x in supported])
                valid = {x["claim_id"] for x in supported}
                sentences = []
                for d in data if isinstance(data, list) else []:
                    ids = [i for i in d.get("claim_ids") or [] if i in valid]
                    sentences.append({"sentence": str(d.get("sentence") or "")[:600], "claim_ids": ids,
                                      "label": "Source-linked" if ids else "AI interpretation"})
                summary["synthesis"] = {"sentences": sentences, "model": meta["model"], "prompt_version": meta["prompt_version"]}
            except ai.AIUnavailable as e:
                summary["synthesis_error"] = str(e)
    with db.db() as con:
        db.update(con, "projects", pid, {"summary": summary})
        audit(con, "Evidence summary built", actor="Academic Integrity Agent", project_id=pid, object_type="project",
              object_id=pid, details=f"{len(claims)} claims", ai=(summary.get("synthesis") or None) and
              {"model": summary["synthesis"]["model"], "prompt_version": summary["synthesis"]["prompt_version"]})
    return summary


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


@api.post("/projects/{pid}/ask")
def ask(pid: str, body: AskIn):
    with db.db() as con:
        b = project_bundle(con, pid)
        require_plan(b["project"])
    refs = [r for r in b["references"] if r["decision"] != "Rejected" and not r.get("demo")]
    if ai.available():
        context = json.dumps({
            "research_question": b["project"]["question"],
            "sources": [{"id": r["id"], "title": r["title"], "year": r["year"], "verification": r["verification_status"],
                         "abstract": (r.get("abstract") or "")[:1200]} for r in refs[:25]],
            "claims": [{"id": c["id"], "text": c["text"], "status": c["status"]} for c in b["claims"]],
        })[:40000]
        try:
            answer, meta = ai.complete(
                "Answer the student's question about their research. Cite sources only by the [id] given, and only for "
                "what their abstract actually says. Label anything else as your reasoning. Point out gaps and limitations.",
                body.question, data=context, inputs=[r["id"] for r in refs[:25]])
            label = f"AI response ({meta['model']}), unverified: check every point against the sources"
        except ai.AIUnavailable as e:
            answer, meta, label = str(e), None, "AI unavailable"
    else:
        meta = None
        label = "Workflow guidance (no AI configured)"
        answer = ("No language model is configured, so here is the standard checklist instead: compare methods, samples "
                  "and settings across your sources; attach exact passages before accepting a claim; run the Red Team on "
                  "each claim; and note limitations the authors report. Add OPENAI_API_KEY to .env to enable AI answers.")
    with db.db() as con:
        db.insert(con, "chat", {"id": db.new_id(), "project_id": pid, "question": body.question, "answer": answer,
                                "ai": {"label": label, **(meta or {})}, "created_at": now()})
        audit(con, "Research assistant consulted", actor="Research assistant" if meta else "Workflow template",
              project_id=pid, object_type="project", object_id=pid, details=body.question[:200], ai=meta)
    return {"answer": answer, "label": label}


# ------------------------------------------------------------------ citations & export

@api.get("/projects/{pid}/bibliography")
def get_bibliography(pid: str, style: str = "APA 7"):
    with db.db() as con:
        b = project_bundle(con, pid)
        counts = {r["id"]: r["claim_count"] for r in b["references"]}
    eligible = [r for r in b["references"] if workflow.citable(r)]
    with db.db() as con:
        full = {r["id"]: db.get(con, "refs", r["id"]) for r in eligible}
    try:
        entries = citations.bibliography(list(full.values()), style)
    except ValueError as e:
        raise HTTPException(400, str(e))
    for e in entries:
        e["risks"] = citations.risk_review(full[e["reference_id"]], counts.get(e["reference_id"], 0))
    excluded = [{"id": r["id"], "title": r["title"], "why":
                 "demo data" if r.get("demo") else "rejected by you" if r["decision"] == "Rejected" else
                 "awaiting your accept/reject decision" if r["decision"] == "Pending" else
                 f"metadata {r['verification_status']} and not reviewed"}
                for r in b["references"] if not workflow.citable(r)]
    return {"style": style, "entries": entries, "excluded": excluded, "blockers": b["export_blockers"],
            "styles": list(citations.STYLES)}


def project_disclosure(con, pid: str) -> dict:
    generated = governance.disclosure(governance.usage(con, pid))
    saved = db.setting(con, f"disclosure:{pid}", "")
    return {"generated": generated, "saved": saved, "text": saved or generated}


@api.get("/projects/{pid}/disclosure")
def get_disclosure(pid: str):
    with db.db() as con:
        load_project(con, pid)
        return project_disclosure(con, pid)


class DisclosureIn(BaseModel):
    text: str = Field(default="", max_length=4000)


@api.put("/projects/{pid}/disclosure")
def save_disclosure(pid: str, body: DisclosureIn):
    """Save the student's own wording; an empty text goes back to the generated version."""
    with db.db() as con:
        load_project(con, pid)
        db.set_setting(con, f"disclosure:{pid}", body.text.strip())
        audit(con, "AI-use disclosure " + ("edited" if body.text.strip() else "reset to generated"),
              project_id=pid, object_type="project", object_id=pid)
        return project_disclosure(con, pid)


@api.get("/projects/{pid}/export")
def export_bibliography(pid: str, style: str = "APA 7", fmt: str = "txt"):
    data = get_bibliography(pid, style)
    if data["blockers"]:
        raise HTTPException(409, "Export checkpoint: " + " ".join(data["blockers"]))
    entries = data["entries"]
    with db.db() as con:
        p = load_project(con, pid)
        refs = [db.get(con, "refs", e["reference_id"]) for e in entries]
        note = project_disclosure(con, pid)["text"]
        db.update(con, "projects", pid, {"exported_at": now()})
        audit(con, "Bibliography exported", actor="Academic Integrity Agent", project_id=pid, object_type="project",
              object_id=pid, details=f"{style}, {fmt}, {len(entries)} references")
    safe_name = "".join(ch for ch in p["title"] if ch.isalnum() or ch in " -_")[:40].strip() or "bibliography"
    if fmt == "html":
        body = ("<!doctype html><meta charset='utf-8'><title>References</title><style>body{font-family:Georgia,serif;"
                "max-width:760px;margin:40px auto;line-height:1.6}p{padding-left:2em;text-indent:-2em}</style><h1>References</h1>"
                + "".join(f"<p>{e['html']}</p>" for e in entries)
                + f"<h2>AI-use disclosure</h2><div>{html.escape(note)}</div>")
        return Response(body, media_type="text/html", headers={"Content-Disposition": f'attachment; filename="{safe_name}.html"'})
    if fmt == "bib":
        header = "".join(f"% {line}\n" for line in textwrap.wrap("AI-use disclosure: " + note, 96))
        return PlainTextResponse(header + "\n" + citations.bibtex(refs), headers={"Content-Disposition": f'attachment; filename="{safe_name}.bib"'})
    if fmt == "csl":
        return JSONResponse([citations.csl_item(r) for r in refs], headers={"Content-Disposition": f'attachment; filename="{safe_name}.json"'})
    return PlainTextResponse("References\n\n" + "\n\n".join(e["text"] for e in entries) + "\n\n\nAI-use disclosure\n\n" + note + "\n",
                             headers={"Content-Disposition": f'attachment; filename="{safe_name}.txt"'})


# ------------------------------------------------------------------ audit, backup, demo

@api.get("/audit")
def audit_log(project: str = "", limit: int = 300):
    with db.db() as con:
        if project:
            ev = con.execute("SELECT * FROM audit_events WHERE project_id = ? ORDER BY created_at DESC LIMIT ?", (project, limit))
        else:
            ev = con.execute("SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?", (limit,))
        events = db.rows(ev)
        runs = db.rows(con.execute("SELECT * FROM agent_runs " + ("WHERE project_id = ? " if project else "") +
                                   "ORDER BY started_at DESC LIMIT 50", (project,) if project else ()))
    return {"events": events, "agent_runs": runs}


@api.get("/backup")
def backup():
    tables = ["projects", "refs", "verification_results", "claims", "evidence_records", "review_decisions",
              "audit_events", "agent_runs", "chat", "settings"]
    with db.db() as con:
        dump = {t: db.rows(con.execute(f"SELECT * FROM {t}")) for t in tables}
    dump["exported_at"] = now()
    return JSONResponse(dump, headers={"Content-Disposition": 'attachment; filename="veritas-backup.json"'})


@api.post("/demo/reset")
def demo_reset():
    with db.db() as con:
        con.execute("DELETE FROM projects WHERE demo = 1")
        seed_demo(con)
    return {"ok": True}


@api.delete("/demo")
def demo_remove():
    with db.db() as con:
        con.execute("DELETE FROM projects WHERE demo = 1")
        db.set_setting(con, "demo_removed", True)
        audit(con, "Demo data removed")
    return {"ok": True}


@api.post("/import/legacy")
async def import_legacy(request: Request):
    """Import a JSON backup exported by the earlier browser-only version (localStorage 'veritas-v1')."""
    try:
        old = await request.json()
    except ValueError:
        raise HTTPException(400, "Not a JSON file.")
    if not isinstance(old, dict) or "projects" not in old:
        raise HTTPException(400, "This does not look like an old VERITAS workspace export.")
    imported = {"projects": 0, "references": 0, "claims": 0}
    with db.db() as con:
        pmap = {}
        for p in old.get("projects") or []:
            # Skip the old version's built-in sample project ("p1").
            if not p.get("title") or (p.get("id") == "p1" and "customer retention" in (p.get("title") or "").lower()):
                continue
            pid = db.new_id()
            pmap[p.get("id")] = pid
            db.insert(con, "projects", {"id": pid, "title": str(p["title"])[:200], "question": str(p.get("question") or p["title"])[:2000],
                                        "created_at": now()})
            imported["projects"] += 1
        if not pmap:
            raise HTTPException(400, "No non-demo projects found in the file.")
        first = next(iter(pmap.values()))
        smap = {}
        by_title = {p["title"]: pmap[p["id"]] for p in old.get("projects") or [] if p.get("id") in pmap}
        for s in old.get("sources") or []:
            if s.get("demo") or not s.get("title"):
                continue
            rid = db.new_id()
            smap[s.get("id")] = rid
            pid = by_title.get(s.get("folder") or "", first)
            db.insert(con, "refs", {"id": rid, "project_id": pid, "title": str(s["title"])[:500],
                                    "authors": parse_authors(str(s.get("authors") or "")), "year": str(s.get("year") or ""),
                                    "doi": scholarly.clean_doi(str(s.get("doi") or "")), "journal": str(s.get("journal") or ""),
                                    "volume": str(s.get("volume") or ""), "issue": str(s.get("issue") or ""), "pages": str(s.get("pages") or ""),
                                    "url": str(s.get("url") or ""), "notes": str(s.get("notes") or ""),
                                    "tags": [t.strip() for t in str(s.get("tags") or "").split(",") if t.strip()],
                                    "fulltext": str(s.get("text") or ""), "fulltext_origin": "Imported from old workspace" if s.get("text") else "",
                                    "metadata_source": "Imported from old workspace", "created_at": now(), "updated_at": now()})
            imported["references"] += 1
        for c in old.get("claims") or []:
            pid = pmap.get(c.get("project"))
            if not pid or not c.get("statement"):
                continue
            cid = db.new_id()
            db.insert(con, "claims", {"id": cid, "project_id": pid, "text": str(c["statement"])[:2000],
                                      "claim_type": "ai_interpretation" if c.get("type") == "AI reasoning" else "source_finding",
                                      "created_at": now(), "updated_at": now()})
            if c.get("source") in smap and c.get("passage"):
                ref = db.get(con, "refs", smap[c["source"]])
                loc = evidence.locate(c["passage"], ref)
                db.insert(con, "evidence_records", {"id": db.new_id(), "claim_id": cid, "reference_id": ref["id"],
                                                    "passage": c["passage"], "location": loc.get("location") or "",
                                                    "page": str(c.get("page") or ""), "match": loc["match"], "created_at": now()})
            recompute_claim(con, cid)
            imported["claims"] += 1
        audit(con, "Old workspace imported", details=json.dumps(imported))
    return imported


# ------------------------------------------------------------------ app

def create_app() -> FastAPI:
    db.init_db()
    with db.db() as con:
        empty = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
        if empty and not db.setting(con, "demo_removed", False):
            seed_demo(con)
        ai.ENABLED = bool(db.setting(con, "ai_enabled", False))
    app = FastAPI(title="VERITAS AI", version=APP_VERSION)
    app.include_router(api)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def no_stale_assets(request: Request, call_next):
        # Always revalidate the front-end files so a teammate's edit shows up on reload.
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(ROOT / "index.html", headers={"Cache-Control": "no-cache"})

    return app
