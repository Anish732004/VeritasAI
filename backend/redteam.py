"""Research Red Team / Contradiction Radar.

Two parts:
 * rule checks on every claim (overgeneralisation, causal language on weak evidence,
   single-source claims, unverified sources, AI interpretation);
 * a counter-evidence search: the claim's concepts plus challenge terms, run through
   OpenAlex, with the most relevant abstract sentence quoted for each result. The stance
   (supports / qualifies / challenges / unclear) comes from the language model when one is
   configured, otherwise from transparent cue-word rules. Either way it is labelled.
"""
import re
from datetime import date

from . import ai, scholarly
from .concepts import rule_based_groups
from .search import _quote
from .text import fold, split_sentences, tokens

OVERGENERAL = re.compile(r"\b(always|never|all|every|none|proves?|proven|guarantees?|certainly|definitely|undeniabl\w*)\b", re.I)
CAUSAL = re.compile(r"\b(causes?|caused|leads? to|results? in|drives?|increases?|decreases?|improves?|reduces?|boosts?)\b", re.I)

CHALLENGE_TERMS = ["limitation", "no significant", "mixed", "negative effect", "did not", "however", "risk", "concern",
                   "fails", "backfire"]
STRONG_CUES = re.compile(r"\b(no significant|not significant|did not|does not|do not|failed to|fails to|negative(ly)? (effect|impact|association)|decreas\w*|reduc\w* (trust|satisfaction|performance)|backfir\w*|harm\w*|no evidence)\b", re.I)
QUALIFY_CUES = re.compile(r"\b(however|but|only (when|if|for)|depend\w*|moderat\w*|limited|limitation\w*|mixed|varies|vary|conditional|in some|concern\w*|risk\w*|caution|trade-?off|paradox)\b", re.I)


def rule_checks(claim: dict, evidence: list[dict], refs: dict[str, dict]) -> list[dict]:
    text = claim.get("text", "")
    alerts = []
    m = OVERGENERAL.search(text)
    if m:
        alerts.append({"kind": "Overgeneralisation", "detail": f"“{m.group(0)}” makes a universal claim. Which populations, settings or periods could be exceptions?"})
    support = [e for e in evidence if e.get("stance", "supports") == "supports" and e.get("match") in ("exact", "near")]
    c = CAUSAL.search(text)
    if c and (not support or all(e.get("location") == "abstract" for e in support)):
        alerts.append({"kind": "Causal language", "detail": f"“{c.group(0)}” implies cause and effect. Check whether the study design (experiment vs survey/correlation) supports that."})
    if not support and claim.get("claim_type") != "ai_interpretation":
        alerts.append({"kind": "Missing evidence", "detail": "No located supporting passage. Link one, relabel it as interpretation, or drop it."})
    elif len({e.get("reference_id") for e in support}) == 1:
        alerts.append({"kind": "Single source", "detail": "Supported by one source only. Is there a second independent study?"})
    for e in support:
        r = refs.get(e.get("reference_id")) or {}
        if r and r.get("verification_status") not in ("Verified match",):
            alerts.append({"kind": "Source not fully verified", "detail": f"“{(r.get('title') or '')[:60]}” has metadata status {r.get('verification_status')}."})
            break
    if claim.get("claim_type") == "ai_interpretation":
        alerts.append({"kind": "AI interpretation", "detail": "This is reasoning, not a source finding. Present it as your interpretation or find a source."})
    return alerts


def best_sentence(abstract: str, claim_tokens: set[str]) -> str:
    best, best_score = "", -1.0
    for s in split_sentences(abstract):
        st = set(tokens(s["text"]))
        overlap = len(st & claim_tokens) / (len(claim_tokens) or 1)
        cue = 0.5 if STRONG_CUES.search(s["text"]) else 0.3 if QUALIFY_CUES.search(s["text"]) else 0
        score = overlap + cue
        if score > best_score:
            best, best_score = s["text"], score
    return best


def rule_stance(sentence: str) -> str:
    if STRONG_CUES.search(sentence):
        return "challenges"
    if QUALIFY_CUES.search(sentence):
        return "qualifies"
    return "unclear"


def search_counter_evidence(claim: dict, exclude_dois: set[str]) -> dict:
    groups = [g for g in rule_based_groups(claim["text"]) if g["label"] != "Risks & limitations"]
    required = [g for g in groups if g["required"]][:2] or groups[:2]
    if not required:
        raise ValueError("Could not find topic words in the claim to search with.")
    parts = ["(" + " OR ".join(_quote(t) for t in g["terms"][:6]) + ")" for g in required]
    parts.append("(" + " OR ".join(_quote(t) for t in CHALLENGE_TERMS) + ")")
    query = " AND ".join(parts)
    since = f"{date.today().year - 10}-01-01"
    works, count = scholarly.openalex_search(query, ["is_retracted:false", "type:article", f"from_publication_date:{since}"], per_page=25)
    claim_tokens = set(tokens(claim["text"]))
    results = []
    for w in works:
        if not w.get("abstract") or (w.get("doi") and w["doi"] in exclude_dois):
            continue
        sentence = best_sentence(w["abstract"], claim_tokens)
        if not sentence:
            continue
        w.update({"sentence": sentence, "stance": rule_stance(sentence), "stance_method": "rule-based cue words"})
        results.append(w)
    results.sort(key=lambda w: {"challenges": 0, "qualifies": 1, "unclear": 2}[w["stance"]])
    results = results[:8]
    ai_meta = None
    if ai.available() and results:
        try:
            ai_meta = _ai_stances(claim, results)
        except ai.AIUnavailable:
            ai_meta = None
    return {"query": query, "count": count, "results": results, "ai": ai_meta,
            "note": "Counter-evidence found in the databases searched (OpenAlex, last 10 years). This is not a complete review of disagreement."}


def _ai_stances(claim: dict, results: list[dict]) -> dict:
    items = [{"i": i, "title": r["title"], "abstract": r["abstract"][:1800]} for i, r in enumerate(results)]
    task = ("For each abstract, decide whether it supports, qualifies, challenges, or is unclear about the CLAIM. "
            "Quote one sentence copied exactly from that abstract as the basis. Return a list of objects with keys "
            "i, stance, quote.")
    data, meta = ai.complete_json(task, "CLAIM: " + claim["text"], data=str(items), max_tokens=1500,
                                  inputs=[r["external_id"] for r in results])
    for d in data if isinstance(data, list) else []:
        try:
            r = results[int(d.get("i"))]
        except (TypeError, ValueError, IndexError):
            continue
        quote, stance = str(d.get("quote") or ""), str(d.get("stance") or "").lower()
        # Accept the model's reading only if its quote really is in the abstract.
        if stance in ("supports", "qualifies", "challenges", "unclear") and quote and fold(quote)[:80] in fold(r["abstract"]):
            r.update({"stance": stance, "sentence": quote, "stance_method": f"AI read the abstract ({meta['model']})"})
    return meta


def challenge_questions(claim: dict, evidence_text: str) -> tuple[list[str], dict]:
    task = ("Act as a critical research supervisor. Ask 3 short, specific questions that test this claim: "
            "generalisation, study design, missing counter-evidence. Return a JSON list of strings.")
    data, meta = ai.complete_json(task, "CLAIM: " + claim["text"], data=evidence_text[:6000], max_tokens=400)
    return [str(q) for q in (data if isinstance(data, list) else [])][:3], meta
