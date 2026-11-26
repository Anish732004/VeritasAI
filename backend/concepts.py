"""Turn a research question into an editable concept map (the plan's search terms).

A language model can propose the groups when one is configured. The rule-based path
below always works, offline, and is what the tests exercise:

 1. split the question into topic phrases: question words, filler, evaluative words and the
    verbs that join two ideas ("microfinance REDUCE poverty") end a phrase;
 2. keep compounds whose last word only makes sense with the one before it ("patient
    outcomes", "firm value") and split ones that hold two ideas ("electric vehicle adoption",
    "grading student essays", "employee pro-environmental behaviour");
 3. look each phrase up in the research thesaurus (thesaurus.py) and expand acronyms;
 4. mark the first three topics as required and settings or populations as optional.

Every term records where it came from, so the plan editor can say so.
"""
import re

from . import ai
from .text import RESEARCH_FILLER, STOPWORDS, fold

# The vocabulary lives in thesaurus.py so it can grow without touching the parsing rules.
from .thesaurus import (ACRONYMS, EVALUATIVE, HEAD_CONCEPTS, INSTRUMENT_HEADS, POPULATION_PREFIX,  # noqa: E402
                        SETTING_WORDS, SOFT_HEADS, SYNONYMS, VERBS)

RISK_WORDS = {"risk", "risks", "limitation", "limitations", "challenge", "challenges", "barrier", "barriers",
              "drawback", "drawbacks", "downside", "downsides", "concern", "concerns", "harm", "harms"}
RISK_GROUP = {"label": "Risks & limitations", "required": False,
              "terms": ["risk", "limitation", "privacy concern", "trust", "challenge", "negative effect"]}

# "-ly" words are adverbs ("specifically", "particularly") and never topics; these are real topics.
LY_TOPICS = {"family", "supply", "assembly", "anomaly", "monopoly", "italy", "early", "apply", "reply", "ally", "rely", "butterfly"}


def is_adverb(word: str) -> bool:
    return len(word) > 5 and word.endswith("ly") and word not in LY_TOPICS


AI_PREFIXES = ("ai-powered", "ai-driven", "ai-based", "ai-enabled", "ai-generated", "ml-based")
CONNECTORS = re.compile(r"\b(and|or|in|on|of|for|to|with|by|among|between|within|versus|vs)\b|[,;:?!.()\"]")


def spelling_variants(term: str) -> list[str]:
    out = [term]
    swaps = (("isation", "ization"), ("ization", "isation"), ("ised", "ized"), ("ized", "ised"),
             ("behaviour", "behavior"), ("behavior", "behaviour"), ("colour", "color"), ("organisation", "organization"))
    for a, b in swaps:
        if a in term.lower():
            v = re.sub(a, b, term, flags=re.I)
            if v not in out:
                out.append(v)
    return out


def _base_verb(word: str) -> str | None:
    """The verb a word is a form of ("reduces", "reduced", "reducing" -> "reduce"), if it is one."""
    if word in VERBS:
        return word
    for suffix, add in (("ies", "y"), ("ied", "y"), ("es", ""), ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e"), ("s", ""), ("d", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            stem_ = word[: -len(suffix)] + add
            if stem_ in VERBS:
                return stem_
    return None


def _capitals(question: str) -> dict[str, str]:
    """Acronyms in the question ("US", "SMEs", "COVID-19"): kept as typed and never dropped as stopwords."""
    return {fold(t): t for t in re.findall(r"[A-Za-z0-9][\w-]*", question or "") if sum(c.isupper() for c in t) >= 2}


def _casing(question: str) -> dict[str, str]:
    """How the student wrote names ("China", "sub-Saharan", "SMEs"), for display. The first word is skipped."""
    words = re.findall(r"[A-Za-z0-9][\w'’-]*", question or "")
    return {fold(t): t.replace("’", "'") for t in words[1:] if any(c.isupper() for c in t)}


def _breaks(word: str, caps: dict | None = None) -> bool:
    if caps and word in caps and word not in VERBS:
        return False
    if re.fullmatch(r"\d+(\.\d+)?", word):
        return False
    return (word in STOPWORDS or word in EVALUATIVE or len(word) < 2 or is_adverb(word)
            or (word in RESEARCH_FILLER and word not in SOFT_HEADS) or _base_verb(word) is not None)


def _protected_keys() -> list[str]:
    keys = [k for k in SYNONYMS if " " in k]
    return sorted(keys, key=len, reverse=True)


def _phrases(question: str) -> tuple[list[str], bool]:
    """Split the question into candidate topic phrases."""
    caps = _capitals(question)
    text = fold(question)
    # A possessive names whose topic it is: "nurses' turnover intention" -> "nurses , turnover intention".
    # Only plural possessives and people ("women's") are split, so "Alzheimer's disease" stays whole.
    def _possessive(m):
        word = m.group(1)
        if m.group(2) == "s'" or word in POPULATION_HEADS or word in POPULATION_PREFIX:
            return word + ("s" if m.group(2) == "s'" else "") + " ,"
        return m.group(0)
    text = re.sub(r"\b(\w+)('s|s')(?=\s)", _possessive, text)
    # "intention to purchase" -> "purchase intention": the usual name of the concept in papers.
    text = re.sub(r"\b(intentions?|willingness) to (\w+)", r"\2 \1 ,", text)
    # Keep known multi-word concepts ("liquidity risk", "electric vehicle") together.
    for key in _protected_keys():
        text = re.sub(r"(?<![\w-])" + re.escape(key) + r"(?![\w-])", key.replace(" ", "_"), text)
    asks_risk = False
    phrases = []
    for chunk in CONNECTORS.split(text):
        if not chunk or not chunk.strip():
            continue
        current: list[str] = []
        has_key = False

        def flush():
            nonlocal has_key
            if current:
                phrases.append(" ".join(current))
            current.clear()
            has_key = False

        for w in chunk.split():
            w = w.strip("'\"")
            if "_" in w:
                # A known concept keeps the words in front of it ("corporate investment_decisions") and a
                # soft head after it ("supply_chain performance"), but two known concepts never merge.
                if has_key or any(x in SYNONYMS or x in ACRONYMS or x in HEAD_CONCEPTS for x in current):
                    flush()            # "blockchain supply_chain": blockchain is a concept, not a modifier
                current.extend(w.replace("_", " ").split())
                has_key = True
                continue
            if w in AI_PREFIXES:
                flush()
                phrases.append("ai")
                continue
            if w in RISK_WORDS:
                asks_risk = True
                flush()
                continue
            if w in SOFT_HEADS:
                if current:            # "patient outcomes", "esg performance": the head completes the phrase
                    current.append(w)
                    flush()
                elif w in HEAD_CONCEPTS:
                    phrases.append(w)  # "adoption" on its own is still a concept
                continue
            if _breaks(w, caps):
                flush()
                continue
            if has_key:
                flush()                # after a known concept only a soft head attaches; anything else starts anew
            current.append(w)
        flush()
    out = []
    for p in phrases:
        out.extend(_split_compound(p.split()))
    return [p for p in out if p], asks_risk


def _split_compound(ws: list[str]) -> list[str]:
    """Split a phrase that holds two ideas; keep one that is a single idea."""
    joined = " ".join(ws)
    if len(ws) <= 1 or joined in SYNONYMS or _singular(joined) in SYNONYMS:
        return [joined]
    # "electric vehicle adoption": a known concept followed by a head concept is two ideas.
    if ws[-1] in HEAD_CONCEPTS:
        return _split_compound(ws[:-1]) + [ws[-1]]
    # "ai tutoring systems": a known concept in front of other content is a separate idea
    # (not for a lone vague head: "esg performance" stays one phrase).
    if ws[0] in SYNONYMS and " ".join(ws[1:]) not in SYNONYMS and not (len(ws) == 2 and ws[1] in SOFT_HEADS | GENERIC_NOUNS):
        return [ws[0]] + _split_compound(ws[1:])
    # "grading student essays": a leading -ing word is its own idea in a 3+ word phrase.
    if len(ws) >= 3 and ws[0].endswith("ing") and ws[0] not in SOFT_HEADS:
        return [ws[0]] + _split_compound(ws[1:])
    # "employee innovation", "employee pro-environmental behaviour": the population is a setting and
    # the rest is the topic. Kept together when the rest is only a vague head ("employee performance").
    if ws[0] in POPULATION_PREFIX and not (len(ws) == 2 and ws[1] in SOFT_HEADS):
        return [ws[0]] + _split_compound(ws[1:])
    if len(ws) <= 3:
        return [joined]
    # Long runs: take known sub-phrases where possible, otherwise single words.
    out, i = [], 0
    while i < len(ws):
        for n in (3, 2, 1):
            cand = " ".join(ws[i : i + n])
            if cand in SYNONYMS or n == 1:
                out.append(cand)
                i += n
                break
    return out


GENERIC_NOUNS = {"businesses", "business", "companies", "company", "firms", "firm", "sector", "industry", "industries",
                 "context", "settings"}
POPULATION_HEADS = {"consumers", "customers", "users", "students", "employees", "workers", "patients", "adults", "children",
                    "women", "men", "mothers", "fathers", "parents", "farmers", "nurses", "teachers", "managers"}


def display(term: str, caps: dict | None = None) -> str:
    """Write acronyms in capitals inside a term: "green hrm" -> "green HRM", "smes" -> "SMEs" as typed."""
    caps = caps or {}
    return " ".join(caps.get(w) or (ACRONYMS[w][0] if w in ACRONYMS else w) for w in term.split(" "))


def with_acronyms(term: str) -> list[str]:
    """A term plus its spelled-out form when it contains an acronym: "ESG performance" -> also
    "environmental, social and governance performance"."""
    words = term.lower().split(" ")
    if not any(w in ACRONYMS for w in words):
        return [term]
    expanded = " ".join(ACRONYMS[w][1] if w in ACRONYMS else w for w in words)
    return [display(term.lower()), expanded]


def _singular(phrase: str) -> str:
    return phrase[:-1] if phrase.endswith("s") and not phrase.endswith("ss") else phrase


def _lookup(phrase: str, caps: dict | None = None) -> tuple[str, list[str], bool, str]:
    """Map a phrase to (label, terms, is_setting, source). source is "thesaurus" or "question"."""
    if phrase not in SYNONYMS and _singular(phrase) in SYNONYMS:
        phrase = _singular(phrase)
    if phrase in SYNONYMS:
        label, terms = SYNONYMS[phrase]
        return label, list(terms), phrase in SETTING_WORDS, "thesaurus"
    if phrase in HEAD_CONCEPTS:
        label, terms = HEAD_CONCEPTS[phrase]
        return label, list(terms), False, "thesaurus"
    if phrase in ACRONYMS and ACRONYMS[phrase][1] in SYNONYMS:
        label, terms = SYNONYMS[ACRONYMS[phrase][1]]
        return label, list(terms), False, "thesaurus"
    ws = phrase.split()
    # A known concept inside a longer phrase ("ceo overconfidence" contains "overconfidence").
    for n in range(len(ws) - 1, 0, -1):
        for i in range(len(ws) - n + 1):
            key = " ".join(ws[i : i + n])
            if key in SYNONYMS and key in SETTING_WORDS and set(ws) - set(key.split()) - GENERIC_NOUNS:
                continue           # "mobile banking apps" is about mobile banking, not about banks as a setting
            if key in SYNONYMS:
                label, terms = SYNONYMS[key]
                rest = set(ws) - set(key.split())
                extra = [] if rest <= GENERIC_NOUNS else [display(phrase, caps)]
                return label, [t for t in extra if t.lower() not in (x.lower() for x in terms)] + list(terms), key in SETTING_WORDS, "thesaurus"
    # Drop a vague trailing noun ("software companies" -> "software"), but keep it as a modifier ("firm value").
    core = ws[:-1] if len(ws) > 1 and ws[-1] in GENERIC_NOUNS else ws
    phrase = " ".join(core)
    terms = [display(phrase, caps)]
    # "corporate investment decisions" -> also "corporate investment"; "esg performance" -> also "ESG";
    # "mindfulness training" -> also "mindfulness".
    if len(core) >= 2 and (core[-1] in SOFT_HEADS or core[-1] in INSTRUMENT_HEADS):
        modifier = core[:-1]
        if len(modifier) >= 2 or modifier[0] in ACRONYMS or core[-1] in INSTRUMENT_HEADS:
            terms.append(display(" ".join(modifier), caps))
    elif len(core) == 3:
        # "international trade flows" -> also "trade flows": papers often use the shorter core phrase.
        terms.append(display(" ".join(core[1:]), caps))
    label = display(phrase, caps)
    is_setting = phrase in SETTING_WORDS or (len(core) >= 2 and core[-1] in POPULATION_HEADS) or phrase in POPULATION_HEADS
    return label[:1].upper() + label[1:], terms, is_setting, "question"


def _expand(terms: list[str]) -> list[str]:
    out: list[str] = []
    for t in terms:
        for a in with_acronyms(t):
            for v in spelling_variants(a):
                if v.lower() not in (x.lower() for x in out):
                    out.append(v)
    return out


def rule_based_groups(question: str) -> list[dict]:
    phrases, asks_risk = _phrases(question)
    caps = {**_casing(question), **_capitals(question)}
    groups: list[dict] = []
    seen_labels = set()
    for p in phrases:
        label, terms, is_setting, source = _lookup(p, caps)
        if label.lower() in seen_labels:
            continue
        seen_labels.add(label.lower())
        groups.append({"label": label, "terms": _expand(terms), "required": True, "setting": is_setting, "source": source})
    topic = [g for g in groups if not g["setting"]]
    setting = [g for g in groups if g["setting"]]
    for i, g in enumerate(topic):
        g["required"] = i < 3
    for g in setting:
        g["required"] = len(topic) < 2
    ordered = topic + setting
    if asks_risk:
        ordered.append({**RISK_GROUP, "source": "thesaurus"})
    for g in ordered:
        g.pop("setting", None)
    return ordered[:6]


def default_filters() -> dict:
    return {"years": 5, "language": "en", "min_tier": "B", "article_only": True, "include_conferences": True,
            "include_foundational": False}


def template_plan(question: str) -> dict:
    groups = rule_based_groups(question)
    labels = [g["label"] for g in groups if g["required"]]
    return {
        "generated_by": "Rule-based plan: question parsing + built-in research thesaurus (no AI)",
        "themes": [f"How {labels[0].lower()} relates to {labels[1].lower()}" if len(labels) > 1 else f"Evidence on {question}",
                   "Methods, samples and settings used", "Reported limitations, risks and mixed findings"],
        "subquestions": [
            "What do peer-reviewed studies report, and in which settings?",
            "Which methods and sample sizes support those findings?",
            "Where do studies disagree or report limitations?",
        ],
        "inclusion_criteria": ["Peer-reviewed journal articles", "Published within the chosen time window",
                               "Title or abstract covers every required concept", "English language unless changed"],
        "concept_groups": groups,
        "filters": default_filters(),
    }


AI_PLAN_TASK = (
    "You are an expert research librarian helping a university student plan a literature search. Read the research "
    "question and work out (1) the core constructs being studied, (2) the setting, population or application area, and "
    "(3) any risk, limitation or comparison angle. Then return a JSON object with these keys: "
    "note (ONE plain sentence restating what the student is asking, so they can check you understood), "
    "themes (3-5 strings), subquestions (3-5 strings), inclusion_criteria (3-5 strings), "
    "concept_groups (2-6 objects: label, required boolean, terms) and "
    "years (one of 2, 3, 5, 10, 20: how far back relevant work is likely to be) and suggested_filters (object with include_conferences boolean). "
    "Rules for concept_groups: each group is ONE idea and its terms are alternatives (OR) that a relevant paper's title "
    "or abstract would actually contain: synonyms, acronyms and their spelled-out forms, narrower technical terms used in "
    "that field, British and American spellings. 3-8 short phrases per group. Never use question words, filler such as "
    "impact, role, sector, study or specifically, or whole sentences as terms. Prefer the field's own technical vocabulary "
    "over everyday words. Order the groups from most to least essential. Mark required true for every concept "
    "that a relevant paper must actually be about, however many that is: do not limit the number. Mark a group "
    "optional when relevant papers might not name it (a broad setting, a population, a risk or limitation angle, a "
    "comparison) or when it only narrows the topic. Be careful: each required concept narrows the search, so only "
    "require what the question truly cannot do without. "
    "include_conferences should be true for computing, engineering and applied-science topics where peer-reviewed "
    "conference papers are a main publication venue, and false for most medicine, social science and management topics. "
    "Do not invent citations or authors."
)


# Single words that say nothing about a topic when used alone as a search term.
GENERIC_TERMS = {"system", "systems", "data", "model", "models", "method", "methods", "technology", "technologies",
                 "analysis", "approach", "approaches", "application", "applications", "use", "new", "good", "thing", "things"}
ALLOWED_YEARS = (2, 3, 5, 10, 20)  # the choices offered in the Research Studio filter


def _is_filler(text: str) -> bool:
    words = [w for w in fold(text).replace("-", " ").split() if w]
    return not words or all(w in STOPWORDS or w in RESEARCH_FILLER or is_adverb(w) for w in words)


def _clean_term(term) -> str:
    t = re.sub(r"\b(?:OR|AND|NOT)\b", " ", str(term))      # boolean operators are added by the search, not by terms
    t = re.sub(r"[()\[\]{}\"]", " ", t)                      # brackets and quotes
    t = re.sub(r"\s+", " ", t).strip(" '`,;:.")
    if len(t) < 2 or len(t) > 60 or _is_filler(t) or t.lower() in GENERIC_TERMS:
        return ""
    return t


def sanitise_groups(raw) -> list[dict]:
    """Make a model's concept groups safe to search with. Pure function (see tests).

    Junk terms (operators, brackets, generic words, duplicates) are removed, groups with no usable
    term disappear, and at least one group stays required. Only the boolean True counts as
    required, so a vague "yes" cannot add constraints. The number of required groups is not capped:
    the search relaxes the least essential ones if too few papers match.
    """
    if not isinstance(raw, list):
        return []
    groups = []
    for g in raw:
        if not isinstance(g, dict):
            continue
        terms: list[str] = []
        for t in g.get("terms") if isinstance(g.get("terms"), list) else []:
            t = _clean_term(t)
            if t and t.lower() not in (x.lower() for x in terms):
                terms.append(t)
        if not terms:
            continue
        label = re.sub(r"\s+", " ", str(g.get("label") or "")).strip()[:60]
        groups.append({"label": label if label and not _is_filler(label) else terms[0],
                       "required": g.get("required") is True, "terms": terms[:8]})
    groups = groups[:8]
    if groups and not any(g["required"] for g in groups):
        groups[0]["required"] = True
    return groups


def validate_ai_plan(data) -> dict:
    """Turn the model's JSON into a safe plan. Pure function, so it can be tested without a network.

    The model is only trusted for wording; filter suggestions are limited to the choices the
    Research Studio offers, and anything else keeps the defaults.
    """
    if not isinstance(data, dict):
        raise ai.AIUnavailable("AI plan was not an object")
    groups = sanitise_groups(data.get("concept_groups"))
    if not groups:
        raise ai.AIUnavailable("AI plan had no usable concept groups")
    filters = default_filters()
    sug = data.get("suggested_filters") if isinstance(data.get("suggested_filters"), dict) else {}
    years = data.get("years", sug.get("years"))
    if isinstance(years, int) and not isinstance(years, bool) and years in ALLOWED_YEARS:
        filters["years"] = years
    if isinstance(sug.get("include_conferences"), bool):
        filters["include_conferences"] = sug["include_conferences"]

    def lines(key):
        v = data.get(key)
        return [str(x).strip() for x in v if str(x).strip()][:6] if isinstance(v, list) else []

    note = str(data.get("note") or data.get("interpretation") or "").strip()[:400]
    return {"ai_note": note, "themes": lines("themes"), "subquestions": lines("subquestions"),
            "inclusion_criteria": lines("inclusion_criteria"), "concept_groups": groups, "filters": filters}


def ai_plan(question: str, scope: str = "", level: str = "") -> tuple[dict, dict]:
    context = "Research question: " + question
    if scope.strip():
        context += "\nScope given by the student: " + scope.strip()
    if level.strip():
        context += "\nAcademic level: " + level.strip()
    data, meta = ai.complete_json(AI_PLAN_TASK, context, max_tokens=1400)
    plan = validate_ai_plan(data)
    plan["generated_by"] = f"AI proposal ({meta['model']}): edit before approving"
    return plan, meta


MIN_SHARE = 3  # a keyword must appear on at least this many of the sampled papers


def related_candidates(phrase: str, existing: list[str], counts: dict[str, int], sampled: int, k: int = 6) -> list[dict]:
    """Alternative terms for `phrase`, from keywords that papers about it carry. Pure function (see tests).

    Narrower variants that already contain the phrase ("telemedicine regulation") and fragments of it
    ("carbon" for "carbon taxes") are left out, because searching the phrase already finds them.
    """
    if sampled < 10:
        return []
    p = fold(phrase).strip()
    have = {fold(t) for t in existing}
    out = []
    for kw, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        if n < MIN_SHARE or kw in have or p in kw or kw in p or _is_filler(kw) or len(kw) > 50:
            continue
        out.append({"term": kw, "papers": n, "of": sampled})
        if len(out) == k:
            break
    return out


def add_suggestions(groups: list[dict], counts_for, max_lookups: int = 4) -> int:
    """For required concepts the thesaurus does not know, attach OpenAlex-based suggestions.

    `counts_for(phrase)` returns (keyword counts, papers sampled). Suggestions are shown to the
    student as optional extras; they are never added to the search on their own.
    """
    done = 0
    for g in groups:
        if done >= max_lookups:
            break
        if g.get("source") != "question" or not g.get("required"):
            continue
        try:
            counts, sampled = counts_for(g["terms"][0])
        except Exception:  # network, rate limit: the plan works without suggestions
            return done
        done += 1
        g["suggestions"] = related_candidates(g["terms"][0], g["terms"], counts, sampled)
    return done


def clean_groups(groups: list[dict]) -> list[dict]:
    out = []
    for g in groups or []:
        terms = [t.strip() for t in (g.get("terms") or []) if isinstance(t, str) and t.strip()]
        if terms:
            out.append({"label": (g.get("label") or terms[0]).strip()[:60], "required": bool(g.get("required")),
                        "terms": list(dict.fromkeys(terms))[:12]})
    return out[:8]
