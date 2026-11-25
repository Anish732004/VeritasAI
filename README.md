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
| `OPENAI_API_KEY`, `OPENAI_MODEL` | AI-proposed plans (the model reads your question, scope and level, explains how it understood the question, and suggests concepts, synonyms and filters, all of which are cleaned and then editable), AI reading of counter-evidence abstracts, Red Team questions, an AI synthesis in the summary and the research assistant. With a key, AI stays off until you turn it on in **Settings → AI features**, which first shows what is sent to OpenAI. Without a key, every feature still works using transparent rule-based methods, and the app says so. |
| `CONTACT_EMAIL` | Identifies the app to OpenAlex/Crossref ("polite pool") for faster, more reliable responses. Sent only to those two services. |
| `OPENALEX_API_KEY` | Only needed if OpenAlex rate-limits you. |

Optional journal list: put `data/journal_list.csv` with the columns `issn,name,list,tier` (tier is `A`, `B` or `C`, for example from ABDC or ABS) to use your own venue tiers instead of the citation-metric fallback.

### Turn on AI (better question understanding)

Without a key, Research Studio builds the concept map from word rules and a synonym list. With a key, a language model reads your question for meaning: it works out which concepts a paper must cover, adds the field's own terms, synonyms and acronyms, decides which concepts are essential (there is no limit on how many are required), explains in one sentence how it understood the question, and suggests a time window and whether conference papers matter. Its answer is cleaned (junk terms and duplicates removed), then **you edit and approve it** before anything is searched. After each search it also **rates how relevant every result is to your question** (from the title and abstract only) and blends the rating into the ranking, so papers that merely share a keyword sink and the best ones rise. Each result shows the rating, a one-sentence reason and, when the model quotes the paper, that quote only if it really appears there. Papers are never removed or accepted for you. If few papers match every required concept, the search relaxes the least essential ones step by step and tells you which.

1. **Get an API key.** Sign in at <https://platform.openai.com/api-keys> and choose *Create new secret key*. Copy it straight away (it is shown once). API use is billed separately from a ChatGPT subscription: add a few dollars of credit under *Billing*. A full demo costs well under $1 with the default model.
2. **Put it in `.env`.** In the project folder run `cp .env.example .env` (Windows: `Copy-Item .env.example .env`), open `.env` and write `OPENAI_API_KEY=sk-...` on one line, with no quotes or spaces. Never share the key or put it in chat, screenshots or GitHub (`.env` is git-ignored).
3. **Restart the server.** Press `Ctrl+C` in the terminal, then start it again (see *Run it*). The server reads `.env` only at start-up.
4. **Settings → Test connection → Turn AI on.** The test sends only the word OK. Turning AI on shows what is shared with OpenAI (your question and scope, claims, source titles and abstracts, linked passages; never whole PDFs, your name or your email) and asks you to confirm. Settings shows these steps with a tick for each one you have done, and explains errors such as a wrong key or no credit.
5. **Research Studio → Regenerate** in the plan. The plan should say *AI proposal* and show *How the question was understood*. Check it, edit anything, approve.

Every AI call is recorded in the Audit Trail and labelled in the app. Turn AI off in Settings at any time.

### Conference papers

Research Studio searches journal articles **and conference papers** by default (untick *Also conference papers* in the plan's filters to turn them off). Conference papers carry a *Conference paper* badge, are cited as conference papers (BibTeX `@inproceedings`) and get a venue tier from, in order:

1. **A ranked list you add.** Put `data/conference_list.csv` with the columns `name,list,tier`, for example `Advances in Neural Information Processing Systems,CORE,A*`. `A*` counts as `A`. Names are matched ignoring years, ordinals and words such as "Proceedings of the", so "2022 IEEE Conf. on X" matches "X". Use a list you trust (for example CORE) and check each entry yourself; none is bundled.
2. **Otherwise the publisher and the series' record:** A for a high h-index and citedness, B for a solid record or a recognised society publisher (IEEE, ACM, IET, Springer, Elsevier and similar) with an established series, and C for the rest.
3. **Proceedings series that bundle many unrelated conferences** (such as *E3S Web of Conferences* or *Lecture Notes in...*) are capped at C, because the series name says nothing about an individual conference.

The tier is a screening aid. It cannot tell you whether a conference reviewed full papers or only abstracts, so check that before relying on a conference paper.

## Backup and restore

**Settings → Backups → Download backup** saves every project, source, claim, evidence link, decision and the audit trail as one JSON file. **Settings → Restore from a backup** adds them back (on a new computer, or after a reinstall):

- Projects that already exist are left untouched, so restoring the same file twice is safe. This is a merge, not a replace: to start from scratch, delete `data/veritas.db` first.
- The sample project is not restored, and whether AI is on is never restored: that is decided on each computer in Settings.
- Dropping a backup into *Research Library → Import from the old version* also works: it is recognised and restored in full.

## Tests (run before every demo)

```bash
.venv/bin/python -m pytest -q
```

These offline tests cover the parts that make judgements: verification tolerances (including the online-first year case and a wrong title on a real DOI), passage matching (PDF hyphenation, near matches, invented passages), claim-status rules, Red Team rules, concept extraction and citation formatting. `tests/test_governance.py` covers the governance controls: AI consent, removing stored text, the disclosure in exports, and that `GOVERNANCE.md` lists every risk in the code.

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
6. **Cite**: export APA 7 (txt, html, BibTeX, CSL-JSON). The exported file ends with the AI-use disclosure built from the audit trail. Show the Audit Trail.
7. **Govern**: open **Trust & Governance**: the risk register with a response to each risk, who is accountable for what, the AI-use and data policy, and live counts of what the guardrails caught.

## Ethics, governance and guardrails

See [GOVERNANCE.md](GOVERNANCE.md), also shown in the app under **Trust & Governance**. Both are built from `backend/governance.py`.

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
  governance.py        risk register, accountability, AI-use and data policy, AI-use disclosure
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

- One local user with no login. Keep the server bound to 127.0.0.1, and don't publish it through a public tunnel: anyone with the link could read or change every project.
- Discovery searches OpenAlex only. "Not found" means not found in Crossref or OpenAlex; it does not mean the work does not exist.
- Venue tiers are a screening aid based on journal citation metrics (or your journal list). They are not a verdict on any individual paper.
- A located passage shows that the source contains those words. It does not prove that the claim follows from them, or that the study is right.
- PDF extraction needs text PDFs, so scanned PDFs (which would need OCR) don't work. Page numbers are PDF file positions, labelled as such.
- The audit log is a local record, not a tamper-proof ledger.
