# VERITAS AI
Every claim deserves evidence. Every source deserves verification.

## Quick launch (no installation)
Open `index.html` in Chrome or Edge. Internet is needed for live academic database requests. If browser CORS restrictions prevent requests, try the local server below. The initial examples are synthetic and explicitly labelled; they are never eligible for verified citations. Data persists in browser localStorage. Export a JSON backup before clearing browser data.

## Full local demo (Windows PowerShell)
Open a terminal in this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Optional: edit .env and add your OpenAI API key
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000
```
Open http://127.0.0.1:8000, go to Settings, enter http://127.0.0.1:8000 as Backend URL, and save. PDF extraction and CSL formatting do not require an OpenAI key. AI requests do. Keep the server bound to localhost; this is not a production multi-user service. On macOS/Linux use `python3 -m venv .venv`, `.venv/bin/pip install -r requirements.txt`, `cp .env.example .env`, and `.venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000`.

## Judge demo
1. Open Overview and show the three integrity indicators (not a scientific score).
2. Open Research Studio, generate and approve the plan, search scholarly databases.
3. Save a result, open Source Verification and check the bibliographic details. Try a deliberately incorrect title with a real DOI to demonstrate mismatch detection.
4. In Library add original source text (or import a PDF with the server), then attach an exact passage in Research Studio.
5. Open Evidence Graph, inspect the claim and accept or reject after reviewing the source. Exact passage matching is not entailment or proof of source authenticity.
6. Open Contradiction Radar and compare two findings; link them for review. Rule-based alerts are not comprehensive contradiction detection.
7. Export verified citations and show the audit ledger.

## Architecture and limitations
Vanilla HTML/CSS/JS rather than React/Tailwind, chosen for a dependency-free, immediately launchable hackathon demo. FastAPI optional server, browser localStorage rather than PostgreSQL. Five specialised workflow roles share a local record store; not five independently running LangGraph agents. AI planning, contextual chat and red-team comparison call the optional OpenAI server. Evidence extraction is human-directed exact passage matching; metadata matching is conservative and checks a Crossref record or OpenAlex fallback, not simultaneous consensus across both. OpenAlex may require an API key or rate-limit requests. PDF extraction supports text PDFs, not OCR; page markers refer to PDF page positions. Basic browser citations are drafts; the optional CSL engine formats bibliographies but HTML export strips formatting markup for safety. Author-name parsing is approximate. Citation-to-manuscript matching, automated gap discovery, server-side persistence, authentication, robust production security, and full-text retrieval are not implemented. No external API credentials are included. API calls and installed backend dependencies need testing on your machine; JavaScript syntax and Python compilation were checked locally. The audit log is editable local data, not tamper-proof. The provided hackathon rules and scoring rubric were not attached, so compliance with those separate documents is not confirmed.
