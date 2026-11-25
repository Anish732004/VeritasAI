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
    "remote work": ("Remote work", ["remote work", "telework", "work from home", "hybrid work"]),
}

# Phrases that describe a setting/population; they become optional groups when the
# question already has two required topic groups.
SETTING_WORDS = {"bank", "banks", "banking", "ecommerce", "e-commerce", "retail", "online shopping", "healthcare",
                 "hospital", "hospitals", "higher education", "university", "universities", "school", "schools",
                 "students", "smes", "sme", "firms", "companies", "organisations", "organizations", "india", "uk",
                 "china", "europe", "united states", "usa", "developing countries"}

RISK_WORDS = {"risk", "risks", "limitation", "limitations", "challenge", "challenges", "barrier", "barriers",
              "drawback", "drawbacks", "downside", "downsides", "concern", "concerns", "harm", "harms"}
RISK_GROUP = {"label": "Risks & limitations", "required": False,
              "terms": ["risk", "limitation", "privacy concern", "trust", "challenge", "negative effect"]}

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
            if w in STOPWORDS or w in RESEARCH_FILLER or len(w) < 2:
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
    return {"years": 5, "language": "en", "min_tier": "B", "article_only": True, "include_foundational": False}


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


def ai_plan(question: str) -> tuple[dict, dict]:
    task = ("Create a literature-search plan. Return an object with keys: themes (3-5 strings), subquestions "
            "(3-5 strings), inclusion_criteria (3-5 strings), concept_groups (2-5 objects with label, required "
            "boolean, terms: 3-7 short search phrases including British/American spellings). Mark at most 3 groups "
            "required; settings, populations and risk/limitation themes are optional. No citations.")
    data, meta = ai.complete_json(task, "Research question: " + question, max_tokens=900)
    groups = []
    for g in (data.get("concept_groups") or [])[:6]:
        terms = [str(t).strip() for t in g.get("terms") or [] if str(t).strip()][:8]
        if terms:
            groups.append({"label": str(g.get("label") or terms[0])[:60], "required": bool(g.get("required")), "terms": terms})
    if not groups:
        raise ai.AIUnavailable("AI plan had no concept groups")
    plan = {
        "generated_by": f"AI proposal ({meta['model']}) — edit before approving",
        "themes": [str(x) for x in data.get("themes") or []][:6],
        "subquestions": [str(x) for x in data.get("subquestions") or []][:6],
        "inclusion_criteria": [str(x) for x in data.get("inclusion_criteria") or []][:6],
        "concept_groups": groups,
        "filters": default_filters(),
    }
    return plan, meta


def clean_groups(groups: list[dict]) -> list[dict]:
    out = []
    for g in groups or []:
        terms = [t.strip() for t in (g.get("terms") or []) if isinstance(t, str) and t.strip()]
        if terms:
            out.append({"label": (g.get("label") or terms[0]).strip()[:60], "required": bool(g.get("required")),
                        "terms": list(dict.fromkeys(terms))[:12]})
    return out[:8]
