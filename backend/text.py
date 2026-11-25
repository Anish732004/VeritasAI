"""Text normalisation, tokenising and similarity helpers shared by every agent.

Everything here is deterministic so that verification and evidence matching can be
tested and repeated exactly.
"""
import html
import math
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

STOPWORDS = set(
    """a an the and or but if then than so of in on at to for from by with without within into onto over under
    about above below between among across after before during through via per as is are was were be been being
    am do does did doing done have has had having can could may might must shall should will would this that
    these those it its they them their there here what which who whom whose when where why how whether not no
    nor any all some each every both either neither such very more most less least much many few other another
    own same also just only too again further once i we you he she our your his her us me my mine ours yours
    let lets get gets got make makes made use used using based across toward towards upon""".split()
)

# Words that describe the research act rather than the research topic.
RESEARCH_FILLER = set(
    """effect effects impact impacts affect affects affected influence influences influenced improve improves improved
    improving role roles relationship relationships study studies research researchers researcher identify identified
    identifies examine examining investigate investigating analysis analyse analyze explore exploring evidence
    help helps helping manage managing management's way ways factor factors outcome outcomes literature review
    current recent new key main important significant level levels extent degree case cases context contexts
    understand understanding assess assessing evaluate evaluating measure measuring towards approach approaches
    find found finding findings work works paper papers article articles question questions""".split()
)

_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
_SENT_RE = re.compile(r"(?<=[.!?])[\"')\]]?\s+(?=[A-Z0-9\"'(\[])")
PAGE_MARK_RE = re.compile(r"\[PDF page (\d+)\]")


def strip_tags(value: str) -> str:
    """Remove markup that Crossref/OpenAlex sometimes embed in titles (<i>, <scp>, <sub>…)."""
    return html.unescape(_TAG_RE.sub("", value or "")).strip()


def fold(value: str) -> str:
    """Lowercase, remove accents and unify dashes/quotes."""
    value = unicodedata.normalize("NFKD", strip_tags(str(value or "")))
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[‐-―−]", "-", value)
    value = re.sub(r"[‘’‚‛]", "'", value)
    value = re.sub(r"[“”„‟]", '"', value)
    return value.lower()


def norm_key(value: str) -> str:
    """Letters and digits only. Used for equality checks that ignore punctuation."""
    return re.sub(r"[^a-z0-9]", "", fold(value))


def norm_spaced(value: str) -> str:
    """Letters/digits separated by single spaces; keeps word boundaries for similarity."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", fold(value))).strip()


def similarity(a: str, b: str) -> float:
    a, b = norm_spaced(a), norm_spaced(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def stem(word: str) -> str:
    """Very small English stemmer: enough to match plural/inflected forms in titles and abstracts."""
    w = word
    for suffix, repl in (("isation", "ization"), ("ised", "ized"), ("ising", "izing"), ("ise", "ize")):
        if w.endswith(suffix) and len(w) > len(suffix) + 3:
            w = w[: -len(suffix)] + repl
            break
    for suffix in ("ations", "ation", "ings", "ing", "ies", "ied", "ers", "ed", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            if suffix in ("ies", "ied"):
                return w[: -len(suffix)] + "y"
            return w[: -len(suffix)]
    return w


def words(value: str) -> list[str]:
    return _WORD_RE.findall(fold(value))


def tokens(value: str, drop_stopwords: bool = True) -> list[str]:
    out = []
    for w in words(value):
        for part in w.split("-"):
            if not part or (drop_stopwords and (part in STOPWORDS or len(part) < 2)):
                continue
            out.append(stem(part))
    return out


def phrase_in(phrase: str, text_tokens: list[str]) -> bool:
    """True when every token of `phrase` appears consecutively in the token list."""
    p = tokens(phrase, drop_stopwords=False)
    if not p:
        return False
    n = len(p)
    return any(text_tokens[i : i + n] == p for i in range(len(text_tokens) - n + 1))


def reconstruct_abstract(inverted_index: dict | None) -> str:
    """OpenAlex stores abstracts as {word: [positions]}; rebuild the plain text."""
    if not inverted_index:
        return ""
    positions = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions)).strip()


def split_sentences(text: str) -> list[dict]:
    """Split text into sentences, remembering the PDF page marker each sentence falls under."""
    out = []
    page = None
    for block in PAGE_MARK_RE.split(text or ""):
        if block.isdigit():
            page = int(block)
            continue
        clean = dehyphenate(block)
        for s in _SENT_RE.split(clean):
            s = s.strip()
            if len(s) >= 25:
                out.append({"text": s, "page": page})
    return out


def dehyphenate(text: str) -> str:
    """Join words broken across PDF lines ("perso-\\nnalisation") and collapse whitespace."""
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text or "")
    return re.sub(r"\s+", " ", text).strip()


def passage_key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", fold(dehyphenate(text)))).strip()


class BM25:
    """Okapi BM25 over a small in-memory set of documents."""

    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.avgdl = (sum(len(d) for d in docs) / len(docs)) if docs else 0
        df = Counter()
        for d in docs:
            df.update(set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in docs]

    def score(self, query: list[str], i: int) -> float:
        tf, dl = self.tf[i], len(self.docs[i]) or 1
        s = 0.0
        for t in set(query):
            if t not in tf:
                continue
            f = tf[t]
            s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
        return s


# ---------------------------------------------------------------- person names

_HONORIFIC = re.compile(r"^(?:(?:dr|prof|professor|mr|mrs|ms|sir|dato'?|datuk|datin|seri|tan sri|tun|puan|encik|haji|hj|ir|ts)\.?\s+)+", re.I)
_DEGREES = {"phd", "md", "msc", "mba", "mphil", "dphil", "frs", "cfa", "cpa", "dds", "dvm", "esq", "jr", "sr", "ii", "iii", "iv"}
_PARTICLES = {"van", "von", "de", "der", "den", "di", "da", "del", "della", "le", "la", "bin", "ibn", "al", "el", "dos", "das", "du", "ter", "ten"}


def _is_postnominal(text: str) -> bool:
    """"D. R. B. D. P. B." (honours), "PhD", "Jr.": things that follow a name but are not a given name."""
    toks = [t for t in re.split(r"[\s,]+", text.strip()) if t]
    if not toks:
        return False
    initials = 0
    for t in toks:
        bare = t.strip(".").lower()
        if bare in _DEGREES:
            continue
        # Initials are single letters ("J.", "D.R.B.") or a short all-capitals run ("DRB"), never a word like "John".
        if re.fullmatch(r"(?:[A-Za-z]\.)+[A-Za-z]?\.?|[A-Za-z]|[A-Z]{2,6}", t):
            initials += len(re.findall(r"[A-Za-z]", t))
            continue
        return False
    # One or two initials are a normal given name ("Smith, J. R."); four or more are honours or degrees.
    return initials >= 4 or all(t.strip(".").lower() in _DEGREES for t in toks)


def parse_person_name(name: str) -> tuple[str, str]:
    """(given, family) from "Given Family", "Family, Given", "Given Family, D. R. B. D." or "Family, Given, Jr."."""
    name = re.sub(r"\s+", " ", strip_tags(name or "")).strip()
    name = _HONORIFIC.sub("", name)
    if "," in name:
        parts = [p.strip() for p in name.split(",")]
        left, rest = parts[0], [p for p in parts[1:] if p]
        if rest and all(_is_postnominal(p) for p in rest):
            name = left            # "Alyas Ahmed, D. R. B. D. P. B." -> the name is "Alyas Ahmed"
        elif rest and len(rest) >= 2 and _is_postnominal(rest[-1]):
            return rest[0], left   # "Smith, John, Jr."
        elif rest:
            return ", ".join(rest) if len(rest) > 1 else rest[0], left
        else:
            name = left
    bits = name.split()
    if not bits:
        return "", ""
    if len(bits) == 1:
        return "", bits[0]
    i = len(bits) - 1
    while i > 1 and bits[i - 1].lower() in _PARTICLES:
        i -= 1
    return " ".join(bits[:i]), " ".join(bits[i:])

