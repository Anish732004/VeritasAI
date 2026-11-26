"""Read a pasted reference list (APA, Vancouver/Nature style, or a web page) into fields.

Rule-based and conservative: a detail that cannot be read is left empty and shown as missing.
Nothing is guessed, and nothing here looks anything up; the Source Integrity Agent checks the
result against Crossref and OpenAlex afterwards.
"""
import re

from .scholarly import clean_doi

DOI_RE = re.compile(r"(?:https?://(?:dx\.)?doi\.org/|doi:\s*)?(10\.\d{4,9}/[^\s\"<>]+)", re.I)
URL_RE = re.compile(r"https?://[^\s\"<>]+", re.I)
APA_YEAR_RE = re.compile(r"\((\d{4})[a-z]?(?:,[^)]*)?\)|\((n\.d\.)\)", re.I)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})[a-z]?\b")
MARKER_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[.)]|([A-Z])[.)])\s+")
# "Kahneman, D.", "Al-Mansoori, K.", "Walker-Smith, J. A.", "Kaiser, Ł."
APA_AUTHOR_RE = re.compile(r"([^\W\d_][\w'’\- ]*?),\s*((?:[^\W\d_]\.\s?(?:-\s?[^\W\d_]\.\s?)?)+)", re.U)
# "LECUN Y", "Bengio Y", "Hinton GE"
VANCOUVER_AUTHOR_RE = re.compile(r"^([^\W\d_][\w'’\-]+(?: [^\W\d_][\w'’\-]+)*) ([A-Z]{1,3})$", re.U)


def _ordinal(m: re.Match) -> int | None:
    num, letter = m.group(1) or m.group(2), m.group(3)
    if num:
        return int(num)
    return ord(letter) - ord("A") + 1 if letter else None


def split_references(text: str) -> list[str]:
    """One string per reference. List markers (A., B., 1., [1]) are used when they run in order, so a wrapped
    line that happens to start "A. (1998)…" is not mistaken for a new reference; otherwise blank lines, then lines."""
    lines = [l.rstrip() for l in (text or "").replace("\r", "").split("\n")]
    last, refs, current = 0, [], []
    starts = [(i, _ordinal(m)) for i, l in enumerate(lines) if (m := MARKER_RE.match(l))]
    if sum(1 for _, n in starts if n is not None) >= 2:
        for l in lines:
            m = MARKER_RE.match(l)
            n = _ordinal(m) if m else None
            # A label starts a new reference only if it comes after the previous one (gaps allowed: B, D, E),
            # so a wrapped line beginning "A. (1998)…" inside reference D stays part of D.
            if n is not None and last < n <= last + 4:
                if current:
                    refs.append(" ".join(current))
                current = [l[m.end():].strip()]
                last = n
            elif l.strip():
                _append(current, l.strip())
        if current:
            refs.append(" ".join(current))
        return [r for r in refs if r]
    if re.search(r"\n\s*\n", text or ""):
        return [" ".join(b.split()) for b in re.split(r"\n\s*\n", text) if b.strip()]
    return [l.strip() for l in lines if l.strip()]


def _append(current: list[str], line: str) -> None:
    """Add a wrapped line. A URL or DOI broken at "-" or "/" is joined without a space."""
    if current and re.search(r"(https?://|doi\.org/|10\.\d{4,9}/)\S*[-/]$", current[-1]):
        current[-1] += line
    else:
        current.append(line)


VANCOUVER_BLOCK_RE = re.compile(r"^((?:[^\W\d_][\w'’\-]+(?: [^\W\d_][\w'’\-]+)* [A-Z]{1,3}(?:,\s*|\.\s+))+)", re.U)


def _authors_apa(block: str) -> list[dict]:
    block = block.replace("&", ",").replace(" and ", ", ")
    return [{"given": g.strip(), "family": f.strip(" ,")} for f, g in APA_AUTHOR_RE.findall(block)]


def _authors_vancouver(block: str) -> list[dict]:
    out = []
    for part in [p.strip() for p in block.split(",") if p.strip()]:
        m = VANCOUVER_AUTHOR_RE.match(part.rstrip("."))
        if not m:
            return []
        family = m.group(1)
        family = family.title() if family.isupper() else family
        out.append({"given": " ".join(c + "." for c in m.group(2)), "family": family})
    return out


def _sentences(s: str) -> list[str]:
    """Split on ". " that ends a sentence, not on initials like "J." or "Ł."."""
    parts = re.split(r"(?<=[^\W\d_]{2}[.?!])\s+|(?<=\d[.])\s+|(?<=[)][.])\s+", s.strip(), flags=re.U)
    return [p.strip() for p in parts if p.strip()]


def parse_reference(raw: str) -> dict:
    """Fields read from one pasted reference. Missing details stay empty."""
    text = " ".join((raw or "").split())
    out = {"raw": text, "title": "", "authors": [], "year": "", "doi": "", "journal": "", "volume": "", "issue": "",
           "pages": "", "url": "", "kind": "journal-article", "format": "unknown"}
    m = DOI_RE.search(text)
    if m:
        out["doi"] = clean_doi(m.group(1).rstrip(".,;)"))
        text = (text[: m.start()] + text[m.end():]).strip()
    urls = [u.rstrip(".,;)") for u in URL_RE.findall(text)]
    if urls:
        out["url"] = urls[0]
        text = URL_RE.sub("", text).strip()
    elif out["doi"]:
        out["url"] = "https://doi.org/" + out["doi"]

    y = APA_YEAR_RE.search(text)
    if y:  # APA: Authors (Year). Title. Journal, vol(issue), pages.
        out["format"] = "APA"
        out["year"] = "" if y.group(2) else y.group(1)
        block = text[: y.start()].strip()  # keep the final "G." so the last author's initial is not lost
        org = block.strip(" .")
        out["authors"] = _authors_apa(block) or ([{"given": "", "family": org}] if org else [])  # organisation
        rest = text[y.end():].lstrip(". ")
        parts = _sentences(rest)
        if parts:
            out["title"] = parts[0].rstrip(".")
        tail = " ".join(parts[1:])
        jm = re.match(r"(.+?),\s*(\d+)\s*(?:\((\d+[\w\-]*)\))?\s*(?:,\s*([\w\-–]+))?", tail)
        if jm:
            out.update({"journal": jm.group(1).strip(), "volume": jm.group(2), "issue": jm.group(3) or "",
                        "pages": (jm.group(4) or "").replace("–", "-").strip(".")})
        elif tail:
            out["journal"] = tail.strip(". ")
    else:
        vb = VANCOUVER_BLOCK_RE.match(text)
        vauthors = _authors_vancouver(vb.group(1).strip().rstrip(".")) if vb else []
        parts = _sentences(text[vb.end():]) if vauthors else _sentences(text)
        if vauthors and parts:  # Vancouver / Nature: AUTHORS. Title. Journal Year;vol:pages.
            out["format"] = "Vancouver"
            out["authors"] = vauthors
            out["title"] = parts[0].rstrip(".")
            tail = " ".join(parts[1:])
            vm = re.match(r"(.+?)\s+((?:19|20)\d{2})\s*;\s*(\d+)\s*(?:\((\d+)\))?\s*:\s*([\w\-–]+)", tail)
            if vm:
                out.update({"journal": vm.group(1).strip(), "year": vm.group(2), "volume": vm.group(3),
                            "issue": vm.group(4) or "", "pages": vm.group(5).replace("–", "-").strip(".")})
            else:
                yy = YEAR_RE.search(tail)
                out["year"] = yy.group(1) if yy else ""
                out["journal"] = tail.split(str(out["year"]))[0].strip(" .;") if tail else ""
        elif out["url"] and not out["doi"]:  # Web page: Title. Organisation. URL
            out["format"] = "web page"
            out["kind"] = "webpage"
            out["title"] = parts[0].rstrip(".") if parts else ""
            if len(parts) >= 2:
                out["authors"] = [{"given": "", "family": parts[1].rstrip(". ")}]
            yy = YEAR_RE.search(" ".join(parts[2:]))
            out["year"] = yy.group(1) if yy else ""
        else:
            out["title"] = parts[0].rstrip(".") if parts else text
            yy = YEAR_RE.search(text)
            out["year"] = yy.group(1) if yy else ""
    if out["url"] and not out["doi"] and not out["journal"] and not out["volume"]:
        out["kind"] = "webpage"
    return out


def same_work(a: dict, b: dict) -> bool:
    """Two references describe the same work: same DOI, or same title words + year + first author's surname."""
    from .verify import _title_tokens
    da, db_ = clean_doi(a.get("doi") or ""), clean_doi(b.get("doi") or "")
    if da and db_:
        return da == db_
    ta, tb = _title_tokens(a.get("title") or ""), _title_tokens(b.get("title") or "")
    if not ta or ta != tb:
        return False
    if a.get("year") and b.get("year") and str(a["year"]) != str(b["year"]):
        return False
    fa = ((a.get("authors") or [{}])[0].get("family") or "").lower()
    fb = ((b.get("authors") or [{}])[0].get("family") or "").lower()
    return not fa or not fb or fa == fb
