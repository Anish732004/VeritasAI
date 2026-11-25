# VERITAS AI

Every claim deserves evidence. Every source deserves verification.

A research-integrity workspace for students: plan a literature search, verify every source against Crossref and OpenAlex, link claims to passages that really exist in the source, look for counter-evidence, approve everything yourself, and export a CSL-formatted bibliography. Every step is recorded in an audit trail.

## Run it

You need Python 3.10 or newer and an internet connection (for OpenAlex and Crossref).

**macOS / Linux**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # optional: add keys, see below
.venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

**Windows (PowerShell)**

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. There is nothing to configure in the browser. On first launch, a clearly labelled sample project is loaded. Its data is synthetic: it can never be verified or cited, and it is excluded from the metrics.

### Optional settings (`.env`)

| Setting | What it turns on |
|---|---|
| `OPENAI_API_KEY`, `OPENAI_MODEL` | AI-proposed plans, AI reading of counter-evidence abstracts, Red Team questions, an AI synthesis in the summary and the research assistant. Without a key, every feature still works using transparent rule-based methods, and the app says so. |
| `CONTACT_EMAIL` | Identifies the app to OpenAlex/Crossref ("polite pool") for faster, more reliable responses. Sent only to those two services. |
| `OPENALEX_API_KEY` | Only needed if OpenAlex rate-limits you. |

Optional journal list: put `data/journal_list.csv` with the columns `issn,name,list,tier` (tier is `A`, `B` or `C`, for example from ABDC or ABS) to use your own venue tiers instead of the citation-metric fallback.

## Tests (run before every demo)

```bash
.venv/bin/python -m pytest -q
```

These 38 offline tests cover the parts that make judgements: verification tolerances (including the online-first year case and a wrong title on a real DOI), passage matching (PDF hyphenation, near matches, invented passages), claim-status rules, Red Team rules, concept extraction and citation formatting.

The full demo flow against the live APIs (it uses a throwaway database):

```bash
VERITAS_LIVE=1 .venv/bin/python -m pytest -q tests/test_api_live.py
```

## Demo script (blueprint section 10)

1. **Discover**: Research Studio → generate the plan → edit concepts → **Approve plan** → **Search OpenAlex**. Each result shows why it matched, its venue tier and its score. The footer shows what was filtered out.
2. **Verify**: **Save & verify** a result: it is checked automatically. In Verification Centre, **Check a reference** with a real DOI (`10.1016/j.jbusres.2020.11.022`) and a wrong title to show a Mismatch with a side-by-side comparison.
3. **Trace**: Evidence Graph → **Add claim** → choose a source → pick a suggested sentence. The claim becomes *Source-supported*, and the reason is shown.
4. **Challenge**: Contradiction Radar → **Run Red Team**. Link a qualifying study; the claim becomes *Contradicted / qualified*.
5. **Approve**: Citation Studio → accept or reject each source and claim. Export stays locked until you do.
6. **Cite**: export APA 7 (txt, html, BibTeX, CSL-JSON) and show the Audit Trail.

## How it is built

```
server.py              entry point (uvicorn server:app)
backend/
  api.py               HTTP routes, checkpoints, audit logging
  workflow.py          stage tracking, approval gates, agent-run logging
  scholarly.py         OpenAlex + Crossref clients (retry, cache, polite headers)
  concepts.py          research question → editable concept map
  search.py            Discovery Agent: filtered, ranked, explained search
  verify.py            Source Integrity Agent: 5-field comparison with tolerances
  evidence.py          Evidence Extraction Agent + claim-status rules
  redteam.py           Research Red Team: rule checks + counter-evidence search
  citations.py         Academic Integrity Agent: CSL bibliography + Citation Risk Review
  ai.py                optional language model (OpenAI), with provenance
  db.py, demo.py       SQLite schema (blueprint data model), sample data
static/                front end: plain ES modules, one file per screen
tests/                 offline logic tests + live end-to-end test
data/veritas.db        your local database (created on first run, not committed)
```

| Blueprint layer | This project |
|---|---|
| Next.js / React + Tailwind | Plain JavaScript ES modules and CSS: no build step, so everyone on the team can run it |
| Python + FastAPI | ✓ |
| LangGraph or equivalent | A small explicit workflow (`workflow.py`): five narrow agents, persisted runs, three enforced human checkpoints |
| OpenAI API | ✓, optional; never used to decide whether a paper exists or what it says |
| OpenAlex + Crossref | ✓, with a cache, retries and polite-pool identification |
| PostgreSQL | SQLite with the same entities (Reference, VerificationResult, Claim, EvidenceRecord, ReviewDecision, AuditEvent) |
| CSL citation engine | ✓ citeproc-py with official CSL styles |

## Limits (say these out loud in the demo)

- One local user with no login. Keep the server bound to 127.0.0.1.
- Discovery searches OpenAlex only. "Not found" means not found in Crossref or OpenAlex; it does not mean the work does not exist.
- Venue tiers are a screening aid based on journal citation metrics (or your journal list). They are not a verdict on any individual paper.
- A located passage shows that the source contains those words. It does not prove that the claim follows from them, or that the study is right.
- PDF extraction needs text PDFs, so scanned PDFs (which would need OCR) don't work. Page numbers are PDF file positions, labelled as such.
- The audit log is a local record, not a tamper-proof ledger.
