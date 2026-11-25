"""Evidence Extraction Agent and claim-status rules (blueprint section 5B).

The agent only ever quotes text that exists in a stored abstract or imported full text.
Page numbers come from PDF page markers and are labelled as file positions; they are
never generated.
"""
import re
from difflib import SequenceMatcher

from .text import BM25, PAGE_MARK_RE, passage_key, split_sentences, tokens

# Claim evidence statuses, exactly as named in the blueprint.
SOURCE_SUPPORTED = "Source-supported"
REPORTED = "Reported, not independently checked"
AI_INTERPRETATION = "AI interpretation"
NOT_FOUND = "Not found"
CONTRADICTED = "Contradicted / qualified"
DEMO = "Demo only"

FINDING_CUES = re.compile(r"\b(results?|find(ings?)?|found|show(s|ed|n)?|reveal\w*|indicat\w*|suggest\w*|demonstrat\w*|"
                          r"positive(ly)?|negative(ly)?|significant(ly)?|associated|increase[sd]?|decrease[sd]?|improve[sd]?|enhance[sd]?|reduce[sd]?)\b", re.I)
METHOD_CUES = re.compile(r"\b(survey (was|of)|questionnaire|data (were|was) (collected|analy[sz]ed)|we (collected|employed|used)|"
                         r"sample of|structural equation|methodology|was administered|this (study|paper) (aims|examines|investigates))\b", re.I)


def source_texts(ref: dict) -> list[tuple[str, str]]:
    out = []
    if ref.get("fulltext"):
        out.append(("full text", ref["fulltext"]))
    if ref.get("abstract"):
        out.append(("abstract", ref["abstract"]))
    return out


def suggest(claim: str, ref: dict, k: int = 3) -> list[dict]:
    """Return the k sentences from the source that best match the claim's wording."""
    candidates = []
    for location, text in source_texts(ref):
        for s in split_sentences(text):
            candidates.append({"text": s["text"], "location": location, "page": s["page"]})
    if not candidates:
        return []
    bm = BM25([tokens(c["text"]) for c in candidates])
    q = tokens(claim)

    def weight(text: str) -> float:
        # Prefer sentences that report results over sentences that describe methods.
        if FINDING_CUES.search(text):
            return 1.3
        if METHOD_CUES.search(text):
            return 0.6
        return 1.0

    scored = [(bm.score(q, i) * weight(c["text"]), c) for i, c in enumerate(candidates)]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[0][0] if scored else 1
    out = []
    for sc, c in scored[:k]:
        out.append({**c, "score": round(sc / top, 2),
                    "location_label": location_label(c["location"], c["page"])})
    return out


def location_label(location: str, page) -> str:
    if location == "abstract":
        return "Abstract"
    if page:
        return f"Full text, PDF page {page} (file position; printed page may differ)"
    return "Full text"


def _page_of(key: str, text: str):
    """PDF page on which a normalised passage starts (also when it runs onto the next page)."""
    parts = PAGE_MARK_RE.split(text)
    pages = [(int(parts[i]), passage_key(parts[i + 1])) for i in range(1, len(parts) - 1, 2)]
    for i, (num, body) in enumerate(pages):
        joined = body + (" " + pages[i + 1][1] if i + 1 < len(pages) else "")
        if key in body or (key in joined and key not in (pages[i + 1][1] if i + 1 < len(pages) else "")):
            return num
    return None


def locate(passage: str, ref: dict) -> dict:
    """Find a passage in the source text. Returns match = exact | near | not_located | no_text."""
    texts = source_texts(ref)
    if not texts:
        return {"match": "no_text", "location": "", "page": None, "score": None}
    key = passage_key(passage)
    if len(key) < 15:
        return {"match": "not_located", "location": "", "page": None, "score": 0.0,
                "note": "Passage is too short to locate reliably."}
    best = {"match": "not_located", "location": "", "page": None, "score": 0.0}
    for location, text in texts:
        norm_text = passage_key(text)
        if key in norm_text:
            page = _page_of(key, text) if location == "full text" else None
            return {"match": "exact", "location": location, "page": page, "score": 1.0}
        sentences = split_sentences(text)
        windows = [(s["text"], s["page"]) for s in sentences]
        windows += [(a["text"] + " " + b["text"], a["page"]) for a, b in zip(sentences, sentences[1:])]
        for w, page in windows:
            wk = passage_key(w)
            if abs(len(wk) - len(key)) > max(len(key), 40):
                continue
            sm = SequenceMatcher(None, key, wk, autojunk=False)
            ratio = sm.ratio()
            # Also allow a passage that is a near-exact excerpt of a longer sentence.
            block = max((b.size for b in sm.get_matching_blocks()), default=0) / max(1, len(key))
            score = max(ratio, block if block > 0.97 else 0)
            if score > best["score"]:
                best = {"match": "near" if score >= 0.9 else "not_located", "location": location,
                        "page": page if location == "full text" else None, "score": round(score, 3)}
    if best["match"] != "near":
        best["location"], best["page"] = "", None
    return best


def claim_status(claim: dict, evidence: list[dict], refs: dict[str, dict]) -> tuple[str, str, str]:
    """Return (status, reason, evidence_level) for a claim. Pure function; see tests."""
    if claim.get("demo"):
        return DEMO, "Synthetic illustration attached to demo data; not scholarly evidence.", ""
    if claim.get("claim_type") == "ai_interpretation":
        return AI_INTERPRETATION, "Marked as a synthesis or inference, not a direct source finding.", ""
    support = [e for e in evidence if e.get("stance", "supports") == "supports"]
    counter = [e for e in evidence if e.get("stance") in ("challenges", "qualifies")]
    located = [e for e in support if e.get("match") in ("exact", "near")]
    unchecked = [e for e in support if e.get("match") == "no_text"]

    def cite(e):
        r = refs.get(e.get("reference_id")) or {}
        return (r.get("title") or "source")[:60]

    if counter:
        kinds = sorted({e["stance"] for e in counter})
        reason = (f"{len(counter)} linked source passage(s) " + " / ".join(kinds) + " this claim"
                  + (f", alongside {len(located)} supporting passage(s)" if located else "") + ". Review both before relying on it.")
        return CONTRADICTED, reason, ""
    if located:
        levels = {e.get("location") for e in located}
        level = "full text" if "full text" in levels else "abstract"
        exact = any(e.get("match") == "exact" for e in located)
        reason = (f"Passage {'found word for word' if exact else 'near-matched (formatting differences)'} in the "
                  f"{level} of “{cite(located[0])}”.")
        if level == "abstract":
            reason += " Abstract-level only: check the full paper before relying on details."
        reason += " The underlying study itself has not been independently validated."
        return SOURCE_SUPPORTED, reason, level
    if unchecked:
        return REPORTED, ("A passage is attached but the source text is not stored, so the wording could not be "
                          "checked. Import the abstract or PDF text to check it."), "metadata only"
    if support:
        return NOT_FOUND, "The attached passage could not be located in the stored source text.", ""
    return NOT_FOUND, "No supporting passage is linked to this claim yet.", ""
