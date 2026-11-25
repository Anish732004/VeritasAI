"""Ethics, governance and guardrails, written down once.

The Trust & Governance page, the AI-use disclosure and GOVERNANCE.md all come from here,
so the policy the app shows is the policy the code follows. A test checks that every risk
listed below also appears in GOVERNANCE.md.
"""
import json

from .config import APP_VERSION

PRINCIPLES = [
    ("Evidence before eloquence", "No confident answer without a source trail. A claim is only Source-supported when its passage is found in the stored source text."),
    ("Honest uncertainty", "Say Not found, Partial match or Pending review when the evidence is not there, and say which databases were searched."),
    ("Human approval", "The software recommends; the student accepts, rejects or edits. Nothing is cited or exported without a recorded decision."),
    ("Separate checks", "Checking that a paper exists is kept apart from checking that it supports a claim. A real paper can still fail to support what you wrote."),
]

# Who is accountable for what (a RACI kept deliberately short).
ACCOUNTABILITY = [
    ("Student (you)", "Accountable",
     "The research question, every accept/reject decision, the final claims and citations, the work you submit and its AI-use disclosure."),
    ("VERITAS agents (software)", "Recommend and check",
     "Search, verify metadata, locate passages, look for counter-evidence and format citations. They never accept a source, approve a claim or export on your behalf. Every run is logged."),
    ("Language model (optional)", "Draft only",
     "Suggests plans, reads abstracts for stance, asks challenge questions and drafts a synthesis. Every output is labelled with the model and prompt version. It never decides whether a paper exists, what it says or which page a quote is on."),
    ("Project team (maintainers)", "Responsible for the tool",
     "Keep the verification rules, tests and this policy up to date, run the test suite before every release or demo, and fix reported problems."),
    ("Your institution and supervisor", "Set the rules",
     "Academic-integrity and AI-use policy. Where it differs from this tool's defaults, the institution's policy wins."),
]

AI_MAY = [
    "Suggest search concepts and synonyms, which you edit and approve before any search runs.",
    "Read counter-evidence abstracts and propose a stance; the stance is kept only if its quote is found word for word in that abstract.",
    "Ask Red Team questions that test a claim.",
    "Draft a synthesis from claims you have already linked to passages; each sentence shows the claims it rests on, or is labelled AI interpretation.",
    "Answer questions about your project in the research assistant, labelled as unverified.",
]
AI_MAY_NOT = [
    "Create, complete or correct a reference. Bibliographic details come only from Crossref, OpenAlex or you.",
    "Produce quotations or page numbers. Passages must be found in stored source text; pages come from the PDF itself.",
    "Set a verification status or a claim's evidence status. Those come from fixed, tested rules.",
    "Accept, reject or export anything.",
    "Follow instructions found inside source text. Abstracts and PDFs are passed to it as untrusted data.",
    "Run at all until you turn AI features on in Settings, after being told what data it receives.",
]

DATA_POLICY = [
    ("Where your work is stored", "Only on this computer, in data/veritas.db. There are no accounts, analytics or tracking."),
    ("Sent to OpenAlex and Crossref", "Search terms from your approved plan, and the DOIs and titles being verified. If CONTACT_EMAIL is set, it identifies the app to these two services only."),
    ("Sent to OpenAI (only when you turn AI on)", "Your research question and scope, claims, source titles and abstracts, and the passages you linked. Never whole PDFs, your name or your email address."),
    ("Uploaded PDFs", "Only upload work you are permitted to use (open access, or through your library licence). The PDF file is not kept: only its extracted text, used to locate passages. You can remove it at any time."),
    ("How long it is kept", "Until you delete it. Remove stored text or a source from its side panel, or delete a whole project in Research Studio (its sources, stored text, claims, evidence and assistant answers go with it). The audit trail keeps a short record of past actions so decisions stay accountable; delete data/veritas.db to erase everything."),
    ("Access", "One local user with no login. Keep the server on 127.0.0.1 and do not publish it with a public tunnel: anyone with the link could read or change every project."),
]

# Risk register: the blueprint's section 11, plus risks it does not list.
# status: "In place" = a mechanism enforces it; "Partly" = mitigated with a stated limit.
RISKS = [
    {"risk": "Invented or AI-generated references",
     "response": "Every reference is checked against Crossref and OpenAlex on five fields. Only accepted sources that are a Verified match, or that you overrode with a written reason, can be cited.",
     "where": "verification", "status": "In place", "source": "Blueprint"},
    {"risk": "A real DOI attached to a different paper",
     "response": "Title, authors, year, DOI and journal are compared separately; a disagreement is a Mismatch shown side by side, never silently corrected.",
     "where": "verification", "status": "In place", "source": "Blueprint"},
    {"risk": "A source is missing from one database but exists elsewhere",
     "response": "Results say \"not found in the databases searched\", list which were searched, and offer manual review with a recorded reason.",
     "where": "verification", "status": "In place", "source": "Blueprint"},
    {"risk": "A genuine paper that does not support the claim",
     "response": "Claim evidence is checked separately from metadata. A claim needs a passage found in the source text to be Source-supported.",
     "where": "evidence", "status": "In place", "source": "Blueprint"},
    {"risk": "Plausible but false quotations or page numbers",
     "response": "Passages must be found word for word (or near-identical) in the stored abstract or PDF text. Page numbers come only from PDF page markers and are labelled as file positions.",
     "where": "evidence", "status": "In place", "source": "Blueprint"},
    {"risk": "Full text is inaccessible or copyright-restricted",
     "response": "Work from the abstract and say so (Abstract-level only). Only open-access copies are downloaded; uploads carry a permission notice and can be removed.",
     "where": "evidence", "status": "In place", "source": "Blueprint"},
    {"risk": "Counter-evidence search misses relevant studies",
     "response": "Results are described as counter-evidence found in OpenAlex, not as proof that no disagreement exists.",
     "where": "radar", "status": "Partly", "source": "Blueprint"},
    {"risk": "Overconfident output",
     "response": "Every claim carries one of five evidence labels with its reason, venue tiers explain their basis, and three human checkpoints must be passed.",
     "where": "evidence", "status": "In place", "source": "Blueprint"},
    {"risk": "User data or PDFs exposed",
     "response": "Data stays in a local database; the PDF file is not kept; stored text, sources and projects can be deleted. There is no login, so the server must stay on 127.0.0.1.",
     "where": "settings", "status": "Partly", "source": "Blueprint"},
    {"risk": "Data sent to an AI provider without the student knowing",
     "response": "AI features stay off, even with a key, until the student reads what is sent and turns them on. Every AI call is logged with model, prompt version and inputs.",
     "where": "settings", "status": "In place", "source": "Added"},
    {"risk": "Hiding AI involvement in submitted work",
     "response": "An AI-use disclosure is built from the audit trail of what actually happened in the project, and included in every exported reference list.",
     "where": "citations", "status": "In place", "source": "Added"},
    {"risk": "The tool writes the student's work for them",
     "response": "VERITAS checks and organises evidence; it does not write essays. The AI synthesis only restates claims the student wrote and linked, and is labelled.",
     "where": "evidence", "status": "In place", "source": "Added"},
    {"risk": "Bias towards well-cited, English-language journals",
     "response": "Venue tiers are shown with their basis and called a screening aid. Tier C and any-language options are one click away, and a journal list (e.g. ABDC) can replace the citation metric.",
     "where": "studio", "status": "Partly", "source": "Added"},
    {"risk": "Conference papers of uneven quality",
     "response": "Conference papers are labelled, tiered from a ranked list you can add (such as CORE) or else from the publisher and the series' record, and capped at tier C for proceedings series that bundle many conferences. The tier is a screening aid; check how the conference reviewed its papers.",
     "where": "studio", "status": "Partly", "source": "Added"},
    {"risk": "Over-reliance: treating Source-supported as true",
     "response": "Every Source-supported reason states that the underlying study has not been independently validated. The Red Team looks for counter-evidence on each claim.",
     "where": "radar", "status": "In place", "source": "Added"},
    {"risk": "Instructions hidden in source text (prompt injection)",
     "response": "Abstracts and PDF text are passed to the model as untrusted data, and its output cannot change a status, a reference or a decision.",
     "where": "audit", "status": "In place", "source": "Added"},
    {"risk": "Synthetic demo data mistaken for evidence",
     "response": "Demo sources are labelled everywhere, excluded from metrics, and can never be verified or cited.",
     "where": "overview", "status": "In place", "source": "Added"},
]

GUARDRAILS = [
    ("Five-field reference check", "Title, authors, year, DOI and journal compared against Crossref and OpenAlex, with stated tolerances.", "verification"),
    ("Citable only after review", "Accepted, not demo, and either Verified match or overridden with a reason. Everything else is listed as left out, with why.", "citations"),
    ("Passage must exist in the source", "Exact or near-exact match against stored text; otherwise the claim stays Not found.", "evidence"),
    ("No generated page numbers", "Pages come from PDF page markers and are labelled as file positions.", "evidence"),
    ("AI quotes are checked", "A model's stance on an abstract is discarded unless its quote is in that abstract.", "radar"),
    ("Three enforced checkpoints", "Plan approval before searching, a decision on every source and claim, then export. Enforced by the server, not just the screen.", "citations"),
    ("Citation Risk Review", "Flags missing DOIs, metadata overrides, abstract-only evidence and similar issues on each reference.", "citations"),
    ("Full audit trail", "Every decision, agent run and AI call, with model and prompt version.", "audit"),
]


def _count(con, sql: str, args=()) -> int:
    return con.execute(sql, args).fetchone()[0]


def live_checks(con) -> list[dict]:
    """What the guardrails have actually done in this workspace (real projects only)."""
    real = "SELECT id FROM projects WHERE demo = 0"
    refs = f"SELECT id FROM refs WHERE project_id IN ({real})"
    claims = f"SELECT id FROM claims WHERE project_id IN ({real})"
    return [
        {"label": "Reference checks run", "value": _count(con, f"SELECT COUNT(*) FROM verification_results WHERE reference_id IN ({refs})")},
        {"label": "Checks that flagged a problem", "value": _count(con, f"SELECT COUNT(*) FROM verification_results WHERE reference_id IN ({refs}) AND status IN ('Mismatch', 'Not found', 'Partial match')"),
         "help": "Mismatch, Not found or Partial match"},
        {"label": "Passages found in the source", "value": _count(con, f"SELECT COUNT(*) FROM evidence_records WHERE claim_id IN ({claims}) AND match IN ('exact', 'near')")},
        {"label": "Passages that could not be found", "value": _count(con, f"SELECT COUNT(*) FROM evidence_records WHERE claim_id IN ({claims}) AND match = 'not_located'")},
        {"label": "Your recorded decisions", "value": _count(con, "SELECT COUNT(*) FROM review_decisions WHERE actor = 'Student'")},
        {"label": "AI calls logged", "value": _count(con, f"SELECT COUNT(*) FROM audit_events WHERE ai IS NOT NULL AND project_id IN ({real})")},
    ]


def usage(con, pid: str) -> dict:
    """Facts about one project, taken from the database and audit trail."""
    def n(sql, *args):
        return _count(con, sql, (pid, *args))
    ai_rows = con.execute("SELECT action, ai FROM audit_events WHERE project_id = ? AND ai IS NOT NULL", (pid,)).fetchall()
    models = sorted({(json.loads(r["ai"]) or {}).get("model", "") for r in ai_rows} - {""})
    return {
        "searches": n("SELECT COUNT(*) FROM audit_events WHERE project_id = ? AND action = 'Literature search'"),
        "verified": n("SELECT COUNT(*) FROM refs WHERE project_id = ? AND verification_status != 'Pending review'"),
        "passages": n("SELECT COUNT(*) FROM evidence_records WHERE claim_id IN (SELECT id FROM claims WHERE project_id = ?) AND match IN ('exact', 'near')"),
        "challenged": n("SELECT COUNT(*) FROM audit_events WHERE project_id = ? AND action = 'Red Team challenge'"),
        "decisions": n("SELECT COUNT(*) FROM audit_events WHERE project_id = ? AND actor = 'Student' AND action IN "
                       "('Source accepted', 'Source rejected', 'Claim accepted', 'Claim rejected', 'Plan approved')"),
        "ai_calls": len(ai_rows),
        "ai_tasks": sorted({r["action"] for r in ai_rows}),
        "ai_models": models,
    }


AI_TASK_NAMES = {
    "Plan proposed": "proposing search concepts",
    "Red Team challenge": "reading counter-evidence abstracts and asking challenge questions",
    "Evidence summary built": "drafting a synthesis of my linked claims",
    "Research assistant consulted": "answering questions in the research assistant",
}


def disclosure(u: dict) -> str:
    """A first-person AI-use disclosure, built only from what the audit trail recorded."""
    did = ["plan and run literature searches in OpenAlex" if u["searches"] else "organise my sources",
           f"check the bibliographic details of {u['verified']} reference(s) against Crossref and OpenAlex"]
    if u["passages"]:
        did.append(f"locate {u['passages']} supporting passage(s) in the source texts")
    if u["challenged"]:
        did.append("search for counter-evidence to my claims")
    text = f"I used VERITAS AI (version {APP_VERSION}), a research-integrity tool, to " + ", ".join(did[:-1]) + (" and " if len(did) > 1 else "") + did[-1] + "."
    if u["ai_calls"]:
        tasks = [AI_TASK_NAMES.get(t, t.lower()) for t in u["ai_tasks"]]
        text += (f" A generative AI model ({', '.join(u['ai_models']) or 'OpenAI'}) was used {u['ai_calls']} time(s), for "
                 + ", ".join(tasks) + ". Its output was labelled as AI-generated in the tool, and I checked it against the sources.")
    else:
        text += " No generative AI model was used: planning and critique used rule-based methods."
    text += (" The reference list was formatted by a citation engine from verified metadata, not written by AI. "
             "I read the original sources, made every accept/reject decision myself, and take responsibility for the "
             "final claims, citations and conclusions.")
    return text
