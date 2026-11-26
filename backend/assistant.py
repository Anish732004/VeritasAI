"""Research assistant requests that must never be answered from a model's imagination.

Three kinds are handled by checked, rule-based steps (no AI needed, nothing invented):
 * find   "give me studies that…"  -> Discovery Agent searches OpenAlex; only papers whose title or abstract
            covers every concept count as an answer. Otherwise the answer is "Not found", with related real
            papers that the Source Integrity Agent has checked and labelled.
 * quote  "check this quote…"        -> Evidence Extraction Agent looks for the exact words in the stored source text.
 * note   "save this note…"          -> the note is stored as plain text; instructions inside it are not followed,
            and statuses change only when a check runs.
Anything else goes to the general assistant (AI if switched on, otherwise guidance).
"""
import re

from . import concepts, evidence, scholarly, search, verify
from .text import fold

QUOTE_RE = re.compile(r"[\"“”']([^\"“”]{8,})[\"“”']")
INJECTION_RE = re.compile(r"\b(system|ignore|disregard|override|forget)\b.{0,60}\b(rules?|instructions?|checks?|checking)\b|"
                          r"\bmark\b.{0,40}\b(verified|valid|correct)\b", re.I | re.S)
DISPLAY = {"Verified match": "Verified", "Partial match": "Needs fix", "Pending review": "Not checked"}
# Words that describe the request, not the research topic.
REQUEST_WORDS = {"give", "find", "show", "list", "suggest", "recommend", "need", "want", "three", "two", "five", "some", "few",
                 "peer-reviewed", "peer", "reviewed", "studies", "study", "papers", "paper", "articles", "article",
                 "sources", "source", "references", "evidence", "measure", "measures", "measuring", "research", "me",
                 "please", "any", "published", "academic", "scholarly", "empirical"}


def classify(question: str) -> str:
    q = question.strip()
    if re.search(r"\b(save|add|store|attach|keep)\b.{0,40}\bnotes?\b", q, re.I):
        return "note"
    if QUOTE_RE.search(q) and re.search(r"\b(check|verify|confirm|quote|quotation|said|says|really)\b", q, re.I):
        return "quote"
    if re.search(r"\b(give|find|show|list|suggest|recommend|search for|look for|get me)\b.{0,60}\b(studies|study|papers|articles|"
                 r"sources|references|evidence|research)\b", q, re.I) or \
            re.search(r"\b(are|is) there (any |some )?(peer-reviewed )?(studies|papers|research|articles|evidence)\b", q, re.I):
        return "find"
    return "general"


def _find_ref(question: str, refs: list[dict]) -> dict | None:
    """The library reference a request points at: by an author surname (and year if given) mentioned in it."""
    q = fold(question)
    years = set(re.findall(r"\b(19\d{2}|20\d{2})\b", question))
    best, best_score = None, 0
    for r in refs:
        fams = [fold(a.get("family") or "") for a in r.get("authors") or [] if a.get("family")]
        score = sum(2 for f in fams[:3] if len(f) > 2 and re.search(r"\b" + re.escape(f) + r"\b", q))
        score += 1 if r.get("year") and r["year"] in years else 0
        score += 1 if r.get("verification_status") == verify.STATUS_VERIFIED else 0
        if score > best_score:
            best, best_score = r, score
    return best if best_score >= 2 else None


def handle_note(question: str, refs: list[dict]) -> dict:
    m = QUOTE_RE.search(question)
    note = (m.group(1) if m else re.sub(r"^.*?\bnote\b[^:]*:?", "", question, flags=re.I | re.S)).strip()
    ref = _find_ref(question, refs)
    if not ref:
        return {"kind": "note", "status": "Not saved", "answer": "Which reference should the note go on? I could not tell from the "
                "request (name an author of a paper in this project). Nothing was saved and nothing else changed."}
    warn = INJECTION_RE.search(note)
    answer = (f"Saved as a note on “{ref['title']}”. Notes are stored as plain text: they are content, not commands. "
              f"No status changed; a status changes only when a check runs.")
    if warn:
        answer += (f"\n\nThe note contains an instruction (“{warn.group(0)[:80]}”). It was saved as text and was NOT followed: "
                   "no reference was marked Verified.")
    return {"kind": "note", "status": "Saved as text", "answer": answer, "ref_id": ref["id"], "note": note,
            "instruction_ignored": bool(warn)}


def handle_quote(question: str, refs: list[dict], fetch_abstract=None) -> dict:
    m = QUOTE_RE.search(question)
    quote = m.group(1).strip() if m else ""
    ref = _find_ref(question[m.end():] if m else question, refs) or _find_ref(question, refs)
    if not ref:
        return {"kind": "quote", "status": "Not confirmed", "answer": f"Quote: “{quote}”\n\nThe cited source is not in this "
                "project, so the quote could not be checked. Add the reference first (Verification Centre → Check a reference). "
                "Not confirmed: do not use it as a quotation until you find it in the source."}
    if not (ref.get("abstract") or ref.get("fulltext")) and fetch_abstract:
        ref = {**ref, "abstract": fetch_abstract(ref) or ""}
    loc = evidence.locate(quote, ref)
    cite = f"“{ref['title']}” ({ref.get('year') or 'n.d.'})"
    where = "the stored full text" if ref.get("fulltext") else "the abstract" if ref.get("abstract") else ""
    if loc["match"] in ("exact", "near"):
        status = "Found in source"
        answer = (f"Found in {loc.get('location') or where} of {cite}"
                  + (" (word for word)." if loc["match"] == "exact" else " (near-identical wording; compare it carefully)."))
    elif loc["match"] == "no_text":
        status = "Could not check"
        answer = (f"The text of {cite} is not available here, so the quote could not be checked. Not confirmed: attach the "
                  "PDF (if you are allowed to) or find the sentence in the paper yourself.")
    else:
        status = "Not found in source"
        answer = (f"These words were not found in {where} of {cite}." + (" Only the abstract is stored, so the full paper "
                  "was not checked." if where == "the abstract" else "") + " Not confirmed: do not present it as a quotation "
                  "from this paper.")
    return {"kind": "quote", "status": status, "answer": f"Quote: “{quote}”\n\n{answer}", "ref_id": ref["id"], "match": loc["match"]}


def _topic_groups(question: str) -> list[dict]:
    """Concepts of a find-request, without the words that only describe the request itself."""
    words = [w for w in re.findall(r"[\w'’\-]+", question) if fold(w) not in REQUEST_WORDS]
    groups = [g for g in concepts.rule_based_groups(" ".join(words)) if g["label"] != "Risks & limitations"]
    return [g for g in groups if fold(g["label"]) not in REQUEST_WORDS]


def _general_topic(question: str) -> list[dict]:
    """The general topic of a request without names, places and years ("the AI Club Hackathon 2026 at SP Jain Dubai"
    -> "hackathon"), used to suggest related real papers when nothing answers the exact request."""
    words = re.findall(r"[\w'’\-]+", question)
    kept = []
    for i, w in enumerate(words):
        capital = w[:1].isupper() and i > 0
        if re.fullmatch(r"\d+", w) or (capital and not (len(w) >= 6 and not w.isupper())):
            continue  # a name, place, acronym or year
        kept.append(w.lower() if capital else w)
    return _topic_groups(" ".join(kept))


def handle_find(question: str, check=verify.run, search_fn=None, k: int = 3) -> dict:
    """Search, then answer only with papers that cover every concept of the request. Never fill a gap."""
    search_fn = search_fn or scholarly.openalex_search
    groups = _topic_groups(question)
    if not groups:
        return {"kind": "find", "status": "Not found", "answer": "I could not tell what topic to search for. Nothing was invented."}
    filters = ["is_retracted:false", "type:article|conference-paper|review"]
    q_all = " AND ".join(search._or_block(g) for g in groups)
    searched = []
    try:
        works, n_all = search_fn(q_all, filters, per_page=25)
        searched.append(f"OpenAlex: {q_all} ({n_all} matches)")
    except scholarly.ServiceError as e:
        return {"kind": "find", "status": "Could not check", "answer": f"Could not search, try again ({e}). Nothing was invented."}
    for g in groups:  # required = every concept the student named
        g["required"] = True
    answers = []
    for w in works:
        hits = search.concept_hits(w, groups)
        if all(h["where"] for h in hits):
            answers.append(w)
    related = []
    if len(answers) < k:
        # Related real papers on the general topic (names, places and years removed), relaxed one concept at a
        # time if needed. They are shown as related, never as an answer.
        general = _general_topic(question) or groups
        for drop in range(0, len(general)):
            if drop == 0 and [g["label"] for g in general] == [g["label"] for g in groups]:
                continue
            q = " AND ".join(search._or_block(g) for g in general[: len(general) - drop])
            try:
                more, n = search_fn(q, filters, per_page=10)
            except scholarly.ServiceError:
                break
            searched.append(f"OpenAlex: {q} ({n} matches)")
            related += [w for w in more if w["external_id"] not in {x["external_id"] for x in related + answers}]
            if len(related) >= k:
                break

    def labelled(w):
        ref = {"title": w["title"], "authors": w.get("authors") or [], "year": w.get("year", ""), "doi": w.get("doi", ""),
               "journal": w.get("journal", "")}
        try:
            v = check(ref)
            status = v["status"]
        except Exception:
            status = verify.STATUS_UNCHECKED
        status = DISPLAY.get(status, status)
        covers = [h["label"] for h in search.concept_hits(w, groups) if h["where"]]
        return {"title": w["title"], "year": w.get("year", ""), "doi": w.get("doi", ""), "url": w.get("url", ""),
                "status": status, "covers": covers, "missing": [g["label"] for g in groups if g["label"] not in covers]}

    found = [labelled(w) for w in answers[:k]]
    rel = [labelled(w) for w in related[:k]]
    topic = " + ".join(g["label"] for g in groups)
    lines = []
    if found:
        status = "Found"
        lines.append(f"Papers whose title or abstract covers every part of your request ({topic}), each checked:")
        lines += [f"• [{x['status']}] {x['title']} ({x['year'] or 'n.d.'})" + (f" doi:{x['doi']}" if x["doi"] else "") for x in found]
        if len(found) < k:
            lines.append(f"Only {len(found)} found; nothing was added to make up the number.")
    else:
        status = "Not found"
        lines.append(f"Not found. No study in OpenAlex covers all of: {topic}. I will not invent one.")
    if rel:
        lines.append("\nRelated real papers (they do NOT answer the request; each one checked and labelled):")
        lines += [f"• [{x['status']}] {x['title']} ({x['year'] or 'n.d.'}): covers {', '.join(x['covers']) or 'none'}; "
                  f"does not cover {', '.join(x['missing'])}" for x in rel]
    lines.append("\nSearched: " + " | ".join(searched))
    return {"kind": "find", "status": status, "answer": "\n".join(lines), "found": found, "related": rel, "searched": searched}
