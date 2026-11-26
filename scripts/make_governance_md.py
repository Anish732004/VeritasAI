"""Rebuild GOVERNANCE.md from backend/governance.py:  .venv/bin/python scripts/make_governance_md.py

The policy text lives in the code, so the document and the Trust & Governance page cannot disagree.
Run this after editing backend/governance.py (tests/test_governance.py fails if you forget).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from backend import ai, governance as g  # noqa: E402
from backend.config import PROMPT_VERSION  # noqa: E402

NAMES = {"verification": "Verification Centre", "evidence": "Evidence Graph", "radar": "Contradiction Radar",
         "citations": "Citation Studio", "audit": "Audit Trail", "settings": "Settings", "studio": "Research Studio",
         "overview": "Overview"}
L = []
w = L.append
w("# VERITAS AI: Ethics, Governance and Guardrails\n")
w("This document states how VERITAS AI handles the risks of AI-assisted research. The same content is shown in the app under **Trust & Governance**, and both come from `backend/governance.py`, so the policy you read is the policy the code follows. A test (`tests/test_governance.py`) fails if a risk listed in the code is missing here. Rebuild it with `.venv/bin/python scripts/make_governance_md.py`.\n")
w("Where your institution's academic-integrity or AI-use policy differs from anything below, the institution's policy wins.\n")
w("## 1. Principles\n")
for t, d in g.PRINCIPLES:
    w(f"- **{t}.** {d}")
w("\n## 2. Ethical risks and our response to each\n")
blue = sum(1 for r in g.RISKS if r["source"] == "Blueprint")
w(f"Risks 1 to {blue} come from the blueprint (its problem statement and section 11). Risks {blue + 1} to {len(g.RISKS)} are ones the blueprint does not list. *In place* means code enforces the response; *Partly* means the risk is reduced and the remaining limit is stated.\n")
w("| # | Risk | Response | Status | Where in the app |\n|---|---|---|---|---|")
for i, r in enumerate(g.RISKS, 1):
    w(f"| {i} | {r['risk']} | {r['response']} | {r['status']} | {NAMES[r['where']]} |")
w("\n## 3. Accountability\n")
w("| Who | Role | Accountable for |\n|---|---|---|")
for a, b, c in g.ACCOUNTABILITY:
    w(f"| {a} | {b} | {c} |")
w("\nThe Audit Trail records who did what: every decision by the student, every agent run, and every AI call with its model, prompt version and inputs.\n")
w("## 4. AI-use policy\n")
w("The language model is optional (NVIDIA's API catalog via `NVIDIA_API_KEY`, or OpenAI via `OPENAI_API_KEY`). Without a key, every feature uses transparent rule-based methods. With a key, AI stays **off** until the student turns it on in Settings, after being shown what is sent.\n")
w("**The language model may:**\n")
for x in g.AI_MAY:
    w(f"- {x}")
w("\n**The language model may not:**\n")
for x in g.AI_MAY_NOT:
    w(f"- {x}")
w(f"\n**Instructions sent with every AI request** (prompt version {PROMPT_VERSION}):\n\n> {ai.GUARDRAILS}\n")
w("**Disclosure.** Citation Studio builds a first-person AI-use disclosure for each project from its audit trail: what was searched, how many references were verified, how many passages were located, and every recorded AI call with the model used. The student can edit the wording. The disclosure is added to every exported reference list (.txt, .html and as comment lines in .bib). The CSL-JSON export contains only reference data, because that format has no place for notes.\n")
w("## 5. Guardrails against invented references and false claims\n")
w("| Guardrail | Mechanism | Where |\n|---|---|---|")
for a, b, c in g.GUARDRAILS:
    w(f"| {a} | {b} | {NAMES[c]} |")
w("\nThe offline test suite covers these rules, including a real DOI with a wrong title, an online-first publication year, PDF hyphenation and invented passages. Run it before every demo.\n")
w("## 6. Data and privacy\n")
for t, d in g.DATA_POLICY:
    w(f"- **{t}.** {d}")
w("\n## 7. Reporting a problem\n")
w("If VERITAS marks a real reference as wrong, accepts a wrong one, or locates a passage that is not in the source, record it in the project's notes and tell the project team. The team reproduces it, adds a test case to `tests/test_logic.py`, fixes the rule, and notes the change here. Until it is fixed, use the manual review route (keep your own metadata with a written reason), which the audit trail records.\n")
(pathlib.Path(__file__).resolve().parent.parent / "GOVERNANCE.md").write_text("\n".join(L))
print("GOVERNANCE.md rebuilt:", len(g.RISKS), "risks")
