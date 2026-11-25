"""Academic Integrity Agent: citation formatting and Citation Risk Review.

Bibliographies are produced by a standard CSL engine (citeproc-py with the official CSL
style files) from the reference's structured, reviewed metadata, never from text written
by a language model.
"""
import html
import re

from citeproc import Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle, formatter
from citeproc.source.json import CiteProcJSON

from .text import strip_tags

STYLES = {"APA 7": "apa", "MLA": "modern-language-association", "Harvard": "harvard-cite-them-right",
          "Chicago": "chicago-author-date"}
ALLOWED_TAGS = re.compile(r"&lt;(/?)(i|b|sup|sub)&gt;")


def safe_html(fragment: str) -> str:
    """Escape everything, then re-allow only simple formatting tags produced by the engine."""
    return ALLOWED_TAGS.sub(r"<\1\2>", html.escape(html.unescape(fragment), quote=False))


def csl_item(ref: dict) -> dict:
    authors = []
    for a in ref.get("authors") or []:
        if a.get("family"):
            authors.append({"family": a["family"], "given": a.get("given", "")})
        elif a.get("name"):
            authors.append({"literal": a["name"]})
    item = {"id": ref["id"], "type": "article-journal", "title": strip_tags(ref.get("title", "")),
            "author": authors, "container-title": strip_tags(ref.get("journal", "")), "volume": ref.get("volume", ""),
            "issue": ref.get("issue", ""), "page": ref.get("pages", ""), "DOI": ref.get("doi", "")}
    if not ref.get("doi") and ref.get("url"):
        item["URL"] = ref["url"]
    y = str(ref.get("year") or "")
    if y.isdigit():
        item["issued"] = {"date-parts": [[int(y)]]}
    return {k: v for k, v in item.items() if v not in ("", None, [])}


def in_text(ref: dict, style: str) -> str:
    fams = [a.get("family") or a.get("name", "") for a in ref.get("authors") or []] or ["Unknown author"]
    y = ref.get("year") or "n.d."
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
    data = [csl_item(r) for r in refs]
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
                    "in_text": in_text(by_id[key], style)})
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
    if not (ref.get("volume") or ref.get("pages")):
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
    for r in refs:
        fam = ((r.get("authors") or [{}])[0].get("family") or "anon")
        key = re.sub(r"[^A-Za-z0-9]", "", fam) + str(r.get("year") or "")
        authors = " and ".join(f"{a.get('family', '')}, {a.get('given', '')}".strip(", ") for a in r.get("authors") or [])
        fields = {"title": r.get("title"), "author": authors, "journal": r.get("journal"), "year": r.get("year"),
                  "volume": r.get("volume"), "number": r.get("issue"), "pages": r.get("pages"), "doi": r.get("doi")}
        body = ",\n".join(f"  {k} = {{{str(v).replace('{', '').replace('}', '')}}}" for k, v in fields.items() if v)
        out.append(f"@article{{{key},\n{body}\n}}")
    return "\n\n".join(out)
