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


# Direction of an effect. A cue-word list cannot tell whether a sentence agrees with a claim; comparing the
# direction the claim asserts with the direction the sentence reports can, for simple findings.
UP_WORDS = re.compile(r"\b(increas\w*|improv\w*|enhanc\w*|boost\w*|rais\w*|higher|greater|strengthen\w*|promot\w*|positiv\w*|"
                      r"benefi\w*|gain\w*|facilitat\w*|outperform\w*|more)\b", re.I)
DOWN_WORDS = re.compile(r"\b(decreas\w*|reduc\w*|lower\w*|declin\w*|diminish\w*|weaken\w*|hinder\w*|undermin\w*|negativ\w*|"
                        r"harm\w*|damag\w*|impair\w*|worsen\w*|erod\w*|less)\b", re.I)
NEGATION = re.compile(r"\b(no significant|not significant\w*|insignificant|non-?significant|did not|does not|do not|failed to|fails to|"
                      r"no evidence|no effect|no impact|no relationship|cannot|could not|not found|without any)\b", re.I)
DIRECTION_STEMS = re.compile(UP_WORDS.pattern + "|" + DOWN_WORDS.pattern, re.I)


def direction(text: str) -> int:
    """+1 if the text mostly describes an increase or improvement, -1 a decrease or harm, 0 if unclear or mixed."""
    up, down = len(UP_WORDS.findall(text)), len(DOWN_WORDS.findall(text))
    return 1 if up > down else -1 if down > up else 0


def topic_overlap(sentence: str, claim: str) -> float:
    """Share of the claim's topic words (direction words removed) that the sentence also uses."""
    topic = set(tokens(DIRECTION_STEMS.sub(" ", claim)))
    return len(topic & set(tokens(sentence))) / len(topic) if topic else 0.0


def best_sentence(abstract: str, claim_tokens: set[str]) -> str:
    """The abstract sentence that talks most about the claim's topic and states a finding (not stance-biased)."""
    best, best_score = "", -1.0
    for s in split_sentences(abstract):
        st = set(tokens(s["text"]))
        overlap = len(st & claim_tokens) / (len(claim_tokens) or 1)
        states_finding = bool(UP_WORDS.search(s["text"]) or DOWN_WORDS.search(s["text"]) or NEGATION.search(s["text"]))
        score = overlap + (0.15 if states_finding else 0)
        if score > best_score:
            best, best_score = s["text"], score
    return best


def rule_stance(sentence: str, claim: str = "") -> str:
    """supports / qualifies / challenges / unclear, by comparing the sentence with the claim.

    A first guess from wording, not an understanding of the paper: it only calls a stance when the sentence is
    about the claim's topic, and says "unclear" otherwise. Without a claim it falls back to cue words alone.
    """
    negated, hedged = bool(NEGATION.search(sentence)), bool(QUALIFY_CUES.search(sentence))
    if not claim:
        return "challenges" if negated else "qualifies" if hedged else "unclear"
    if topic_overlap(sentence, claim) < 0.25:
        return "unclear"
    claimed, found = direction(claim), direction(sentence)
    if negated and (found == 0 or found == claimed):
        return "challenges"            # the effect the claim asserts was not found
    if claimed and found:
        if found != claimed:
            return "challenges"        # the finding points the other way
        return "qualifies" if hedged else "supports"
    return "qualifies" if hedged else "unclear"


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
        w.update({"sentence": sentence, "stance": rule_stance(sentence, claim["text"]),
                  "stance_method": "rule-based: compares the direction of the finding with your claim (a rough guess; read the sentence)"})
        results.append(w)
    results.sort(key=lambda w: {"challenges": 0, "qualifies": 1, "supports": 2, "unclear": 3}[w["stance"]])
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
