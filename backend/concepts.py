"""Turn a research question into an editable concept map (the plan's search terms).

A language model can propose the groups when one is configured. The rule-based path
below always works and is what the tests exercise: it removes question words, keeps
2-3 word phrases, expands a small set of well-known synonyms and spelling variants, and
marks the first topic groups as required.
"""
import re

from . import ai
from .text import RESEARCH_FILLER, STOPWORDS, fold

# Known synonyms. Keys are matched against the folded phrase.
SYNONYMS = {
    "ai": ("Artificial intelligence", ["artificial intelligence", "AI", "machine learning", "deep learning"]),
    "artificial intelligence": ("Artificial intelligence", ["artificial intelligence", "AI", "machine learning", "deep learning"]),
    "machine learning": ("Machine learning", ["machine learning", "deep learning", "neural network", "random forest", "gradient boosting"]),
    "deep learning": ("Deep learning", ["deep learning", "neural network", "LSTM"]),
    "generative ai": ("Generative AI", ["generative AI", "large language model", "ChatGPT", "LLM"]),
    "chatbot": ("Chatbots", ["chatbot", "conversational agent", "virtual assistant"]),
    "personalisation": ("Personalisation", ["personalization", "personalisation", "personalized recommendation", "recommender system"]),
    "personalization": ("Personalisation", ["personalization", "personalisation", "personalized recommendation", "recommender system"]),
    "recommendation": ("Recommendations", ["recommender system", "recommendation system", "personalized recommendation"]),
    "customer experience": ("Customer experience", ["customer experience", "customer satisfaction", "user experience"]),
    "customer satisfaction": ("Customer satisfaction", ["customer satisfaction", "customer experience"]),
    "customer retention": ("Customer retention", ["customer retention", "customer loyalty", "churn", "repurchase intention"]),
    "customer loyalty": ("Customer loyalty", ["customer loyalty", "customer retention", "repurchase intention"]),
    "ecommerce": ("E-commerce", ["e-commerce", "ecommerce", "online retail", "online shopping"]),
    "e-commerce": ("E-commerce", ["e-commerce", "ecommerce", "online retail", "online shopping"]),
    "online shopping": ("E-commerce", ["e-commerce", "online retail", "online shopping"]),
    "retail": ("Retail", ["retail", "retailing", "online retail"]),
    "liquidity risk": ("Liquidity risk", ["liquidity risk", "funding liquidity", "liquidity stress", "liquidity coverage ratio", "bank run", "deposit outflow"]),
    "credit risk": ("Credit risk", ["credit risk", "default prediction", "credit scoring", "loan default"]),
    "bank": ("Banking", ["bank", "banking", "financial institution"]),
    "banks": ("Banking", ["bank", "banking", "financial institution"]),
    "banking": ("Banking", ["bank", "banking", "financial institution"]),
    "privacy": ("Privacy", ["privacy", "data protection", "privacy concern"]),
    "trust": ("Trust", ["trust", "consumer trust", "perceived risk"]),
    "students": ("Students", ["students", "higher education", "university students"]),
    "higher education": ("Higher education", ["higher education", "university", "students"]),
    "healthcare": ("Healthcare", ["healthcare", "health care", "hospital", "clinical"]),
    "climate change": ("Climate change", ["climate change", "global warming"]),
    "social media": ("Social media", ["social media", "Instagram", "TikTok", "Facebook"]),
    "mental health": ("Mental health", ["mental health", "depression", "anxiety", "well-being"]),
    "energy": ("Energy", ["energy", "electricity", "power system"]),
    "energy sector": ("Energy", ["energy sector", "power sector", "electricity sector", "energy industry", "energy"]),
    "electricity": ("Electricity", ["electricity", "power system", "electric power"]),
    "electricity generation": ("Electricity generation", ["electricity generation", "power generation", "electric power generation", "power plant"]),
    "power generation": ("Electricity generation", ["power generation", "electricity generation", "electric power generation", "power plant"]),
    "renewable energy": ("Renewable energy", ["renewable energy", "solar", "wind power", "photovoltaic", "clean energy"]),
    "smart grid": ("Smart grid", ["smart grid", "power grid", "grid management", "demand response"]),
    "load forecasting": ("Load forecasting", ["load forecasting", "demand forecasting", "electricity demand prediction"]),
    "predictive maintenance": ("Predictive maintenance", ["predictive maintenance", "fault detection", "condition monitoring"]),
    "supply chain": ("Supply chain", ["supply chain", "logistics", "supply network"]),
    "remote work": ("Remote work", ["remote work", "telework", "work from home", "hybrid work"]),
}

# Phrases that describe a setting/population; they become optional groups when the
# question already has two required topic groups.
SETTING_WORDS = {"manufacturing", "agriculture",
                 "transport", "transportation", "construction", "bank", "banks", "banking", "ecommerce", "e-commerce", "retail", "online shopping", "healthcare",
                 "hospital", "hospitals", "higher education", "university", "universities", "school", "schools",
                 "students", "smes", "sme", "firms", "companies", "organisations", "organizations", "india", "uk",
                 "china", "europe", "united states", "usa", "developing countries"}

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


def _phrases(question: str) -> tuple[list[str], bool]:
    """Split the question into candidate topic phrases (1-3 words)."""
    text = fold(question)
    # Protect known multi-word concepts ("liquidity risk", "customer experience") so the
    # splitter below does not break them apart.
    for key in sorted((k for k in SYNONYMS if " " in k), key=len, reverse=True):
        text = re.sub(r"\b" + re.escape(key) + r"\b", key.replace(" ", "_"), text)
    asks_risk = False
    phrases = []
    for chunk in CONNECTORS.split(text):
        if not chunk or not chunk.strip():
            continue
        current = []
        for w in chunk.split():
            w = w.strip("'\"")
            if "_" in w:
                if current:
                    phrases.append(" ".join(current))
                current = []
                phrases.append(w.replace("_", " "))
                continue
            if w in AI_PREFIXES:
                phrases.append("ai")
                continue
            if w in RISK_WORDS:
                asks_risk = True
                if current:
                    phrases.append(" ".join(current))
                current = []
                continue
            if w in STOPWORDS or w in RESEARCH_FILLER or len(w) < 2 or is_adverb(w):
                if current:
                    phrases.append(" ".join(current))
                current = []
                continue
            current.append(w)
        if current:
            phrases.append(" ".join(current))
    # Long runs of words are split into known sub-phrases where possible.
    out = []
    for p in phrases:
        ws = p.split()
        if len(ws) <= 3:
            out.append(p)
            continue
        i = 0
        while i < len(ws):
            for n in (3, 2, 1):
                cand = " ".join(ws[i : i + n])
                if cand in SYNONYMS or n == 1:
                    out.append(cand)
                    i += n
                    break
    return out, asks_risk


GENERIC_NOUNS = {"businesses", "business", "companies", "company", "firms", "firm", "sector", "industry", "industries",
                 "context", "settings", "platforms", "platform", "users", "consumers", "customers"}


def _lookup(phrase: str) -> tuple[str, list[str], bool]:
    """Map a phrase to (label, terms, is_setting) using the longest known sub-phrase."""
    if phrase in SYNONYMS:
        label, terms = SYNONYMS[phrase]
        return label, list(terms), phrase in SETTING_WORDS
    ws = phrase.split()
    for n in range(len(ws) - 1, 0, -1):
        for i in range(len(ws) - n + 1):
            key = " ".join(ws[i : i + n])
            if key in SYNONYMS:
                label, terms = SYNONYMS[key]
                extra = [phrase] if not set(ws) - {*key.split(), *GENERIC_NOUNS} else []
                return label, list(terms) + [t for t in extra if t not in terms], key in SETTING_WORDS
    core = [w for w in ws if w not in GENERIC_NOUNS] or ws
    phrase = " ".join(core)
    return phrase[:1].upper() + phrase[1:], [phrase], phrase in SETTING_WORDS


def rule_based_groups(question: str) -> list[dict]:
    phrases, asks_risk = _phrases(question)
    groups: list[dict] = []
    seen_labels = set()
    for p in phrases:
        label, terms, is_setting = _lookup(p)
        if label in seen_labels:
            continue
        seen_labels.add(label)
        expanded = []
        for t in terms:
            for v in spelling_variants(t):
                if v.lower() not in (x.lower() for x in expanded):
                    expanded.append(v)
        groups.append({"label": label, "terms": expanded, "required": True, "setting": is_setting})
    topic = [g for g in groups if not g["setting"]]
    setting = [g for g in groups if g["setting"]]
    for i, g in enumerate(topic):
        g["required"] = i < 3
    for g in setting:
        g["required"] = len(topic) < 2
    ordered = topic + setting
    if asks_risk:
        ordered.append(dict(RISK_GROUP))
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
        "generated_by": "Rule-based template (no AI)",
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
    "concept_groups (2-5 objects: label, required boolean, terms) and "
    "years (one of 2, 3, 5, 10, 20: how far back relevant work is likely to be) and suggested_filters (object with include_conferences boolean). "
    "Rules for concept_groups: each group is ONE idea and its terms are alternatives (OR) that a relevant paper's title "
    "or abstract would actually contain: synonyms, acronyms and their spelled-out forms, narrower technical terms used in "
    "that field, British and American spellings. 3-8 short phrases per group. Never use question words, filler such as "
    "impact, role, sector, study or specifically, or whole sentences as terms. Prefer the field's own technical vocabulary "
    "over everyday words. Mark required true only for groups that every relevant paper must mention, at most 3. A "
    "setting or application area is required only when the question has fewer than two other topic groups. Risk and "
    "limitation themes are optional. "
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
    term disappear, at most 3 groups stay required, and at least one is. Only the boolean True
    counts as required, so a vague "yes" cannot widen the constraints.
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
    groups = groups[:6]
    seen = 0
    for g in groups:
        if g["required"]:
            seen += 1
            g["required"] = seen <= 3
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


def clean_groups(groups: list[dict]) -> list[dict]:
    out = []
    for g in groups or []:
        terms = [t.strip() for t in (g.get("terms") or []) if isinstance(t, str) and t.strip()]
        if terms:
            out.append({"label": (g.get("label") or terms[0]).strip()[:60], "required": bool(g.get("required")),
                        "terms": list(dict.fromkeys(terms))[:12]})
    return out[:8]
