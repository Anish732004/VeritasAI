"""Academic Integrity Agent: citation formatting and Citation Risk Review.

Bibliographies are produced by a standard CSL engine (citeproc-py with the official CSL
style files) from the reference's structured, reviewed metadata, never from text written
by a language model.
"""
import html
import re
import unicodedata

from citeproc import Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle, formatter
from citeproc.source.json import CiteProcJSON

from .text import fold, norm_key, strip_tags

STYLES = {"APA 7": "apa", "MLA": "modern-language-association", "Harvard": "harvard-cite-them-right",
          "Chicago": "chicago-author-date"}
ALLOWED_TAGS = re.compile(r"&lt;(/?)(i|b|sup|sub)&gt;")


def safe_html(fragment: str) -> str:
    """Escape everything, then re-allow only simple formatting tags produced by the engine."""
    return ALLOWED_TAGS.sub(r"<\1\2>", html.escape(html.unescape(fragment), quote=False))


def duplicate_key(ref: dict) -> str:
    """Two references are the same work when they share a DOI, or (with no DOI) a title."""
    doi = (ref.get("doi") or "").strip().lower()
    return "doi:" + doi if doi else "title:" + norm_key(ref.get("title") or "")


def dedupe(refs: list[dict]) -> tuple[list[dict], list[tuple[dict, dict]]]:
    """Keep one reference per work. Returns (kept, [(dropped, kept_instead)]).

    The copy kept is the best-checked one (Verified match first), then the earliest saved, so
    the same paper saved several times appears once in the reference list.
    """
    rank = lambda r: (r.get("verification_status") != "Verified match", r.get("created_at") or "", r.get("id") or "")
    best: dict[str, dict] = {}
    for r in sorted(refs, key=rank):
        best.setdefault(duplicate_key(r), r)
    kept = [r for r in refs if best[duplicate_key(r)] is r]
    dropped = [(r, best[duplicate_key(r)]) for r in refs if best[duplicate_key(r)] is not r]
    return kept, dropped


def _ascii(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode())


def year_suffixes(refs: list[dict], style: str) -> dict[str, str]:
    """a, b, c... for different works whose in-text citation would be identical, such as (Hung, 2021)."""
    if style == "MLA":
        return {}
    groups: dict[str, list[dict]] = {}
    for r in refs:
        if str(r.get("year") or "").isdigit():
            groups.setdefault(in_text(r, style), []).append(r)
    out = {}
    for members in groups.values():
        if len(members) > 1:
            for letter, r in zip("abcdefghijklmnopqrstuvwxyz", sorted(members, key=lambda r: fold(strip_tags(r.get("title") or "")))):
                out[r["id"]] = letter
    return out


def bibtex_keys(refs: list[dict]) -> dict[str, str]:
    """A unique BibTeX key per reference: Hung2021, or Hung2021a and Hung2021b when two works would clash."""
    base = {}
    for r in refs:
        fam = _ascii((r.get("authors") or [{}])[0].get("family") or "") or "anon"
        base[r["id"]] = fam + (str(r.get("year") or "") or "nd")
    counts: dict[str, int] = {}
    for k in base.values():
        counts[k] = counts.get(k, 0) + 1
    keys, used = {}, {}
    for r in sorted(refs, key=lambda r: fold(strip_tags(r.get("title") or ""))):
        k = base[r["id"]]
        if counts[k] > 1:
            i = used.get(k, 0)
            used[k] = i + 1
            keys[r["id"]] = k + ("abcdefghijklmnopqrstuvwxyz"[i] if i < 26 else f"_{i}")
        else:
            keys[r["id"]] = k
    return keys


def csl_item(ref: dict) -> dict:
    authors = []
    for a in ref.get("authors") or []:
        if a.get("family"):
            authors.append({"family": a["family"], "given": a.get("given", "")})
        elif a.get("name"):
            authors.append({"literal": a["name"]})
    conference = ref.get("kind") == "conference-paper"
    item = {"id": ref["id"], "type": "paper-conference" if conference else "article-journal", "title": strip_tags(ref.get("title", "")),
            "author": authors, "container-title": strip_tags(ref.get("journal", "")), "volume": ref.get("volume", ""),
            "issue": ref.get("issue", ""), "page": ref.get("pages", ""), "DOI": ref.get("doi", "")}
    if not ref.get("doi") and ref.get("url"):
        item["URL"] = ref["url"]
    y = str(ref.get("year") or "")
    if y.isdigit():
        item["issued"] = {"date-parts": [[int(y)]]}
    return {k: v for k, v in item.items() if v not in ("", None, [])}


def in_text(ref: dict, style: str, suffix: str = "") -> str:
    fams = [a.get("family") or a.get("name", "") for a in ref.get("authors") or []] or ["Unknown author"]
    y = (ref.get("year") or "n.d.") + suffix
    if len(fams) == 1:
        names = fams[0]
    elif len(fams) == 2:
        names = f"{fams[0]} {'&' if style == 'APA 7' else 'and'} {fams[1]}"
    else:
        names = f"{fams[0]} et al."
    if style == "MLA":
        return f"({names})"
    if style == "Chicago":
        return f"({names} {y})"
    return f"({names}, {y})"


def tidy_punctuation(h: str, style: str) -> str:
    """Fix punctuation that citeproc-py does not handle: "Title?." and, for US styles, “Title”."""
    h = re.sub(r"([?!.])((?:</i>)?)\.", r"\1\2", h)
    if style in ("MLA", "Chicago"):
        h = re.sub(r"”([.,])", r"\1”", h)
        h = re.sub(r"([?!])[.,]”", r"\1”", h)
    return h


def sort_key(ref: dict):
    fam = ((ref.get("authors") or [{}])[0].get("family") or (ref.get("authors") or [{}])[0].get("name") or ref.get("title", ""))
    return (fam.lower(), str(ref.get("year") or ""), (ref.get("title") or "").lower())


def bibliography(refs: list[dict], style: str) -> list[dict]:
    if style not in STYLES:
        raise ValueError(f"Unknown style {style}")
    refs = sorted(refs, key=sort_key)
    suffix = year_suffixes(refs, style)
    data = [{**csl_item(r), **({"year-suffix": suffix[r["id"]]} if r["id"] in suffix else {})} for r in refs]
    if not data:
        return []
    bib = CitationStylesBibliography(CitationStylesStyle(STYLES[style], validate=False), CiteProcJSON(data), formatter.html)
    for item in data:
        bib.register(Citation([CitationItem(item["id"])]))
    by_id = {r["id"]: r for r in refs}
    out = []
    # citeproc sorts the bibliography; keep its order and map entries back by position of keys.
    keys = [str(k) for k in bib.keys]
    for key, entry in zip(keys, bib.bibliography()):
        h = tidy_punctuation(safe_html(str(entry)), style)
        out.append({"reference_id": key, "html": h, "text": html.unescape(re.sub(r"<[^>]+>", "", h)),
                    "in_text": in_text(by_id[key], style, suffix.get(key, ""))})
    return out


def risk_review(ref: dict, claims_using: int) -> list[dict]:
    """Citation Risk Review: flags that direct human attention. Not a truth probability."""
    flags = []
    if ref.get("verification_status") != "Verified match":
        level = "high" if ref.get("verification_status") in ("Mismatch", "Not found") else "medium"
        reason = ref.get("override_reason") or "no reason given"
        flags.append({"level": level, "text": f"Metadata status is {ref.get('verification_status')}; you chose to keep your values ({reason})."})
    for field in ("authors", "year", "journal"):
        if not ref.get(field):
            flags.append({"level": "medium", "text": f"Missing {field}."})
    if not ref.get("doi"):
        flags.append({"level": "low", "text": "No DOI; readers will rely on the other details to find it."})
    conference = ref.get("kind") == "conference-paper"
    if conference:
        flags.append({"level": "low", "text": "Conference paper: check the proceedings title, the conference date and place, and the page range "
                      "against the published proceedings. The style may omit \"In\" before the proceedings title; add it by hand if your style needs it."})
    elif not (ref.get("volume") or ref.get("pages")):
        flags.append({"level": "low", "text": "No volume or page range; APA 7 expects them for journal articles where they exist."})
    t = ref.get("title") or ""
    caps = [w for w in re.findall(r"[A-Za-z]+", t) if len(w) > 3]
    if caps and sum(w[0].isupper() for w in caps) / len(caps) > 0.7:
        flags.append({"level": "low", "text": "Title is in Title Case; APA 7 uses sentence case. Adjust by hand to keep proper nouns."})
    if claims_using == 0:
        flags.append({"level": "low", "text": "No claim in this project links to this source."})
    return flags


def bibtex(refs: list[dict]) -> str:
    out = []
    keys = bibtex_keys(refs)
    for r in refs:
        key = keys[r["id"]]
        authors = " and ".join(f"{a.get('family', '')}, {a.get('given', '')}".strip(", ") for a in r.get("authors") or [])
        conference = r.get("kind") == "conference-paper"
        fields = {"title": r.get("title"), "author": authors, ("booktitle" if conference else "journal"): r.get("journal"),
                  "year": r.get("year"), "volume": r.get("volume"), "number": r.get("issue"), "pages": r.get("pages"),
                  "doi": r.get("doi")}
        body = ",\n".join(f"  {k} = {{{str(v).replace('{', '').replace('}', '')}}}" for k, v in fields.items() if v)
        out.append(f"@{'inproceedings' if conference else 'article'}{{{key},\n{body}\n}}")
    return "\n\n".join(out)
