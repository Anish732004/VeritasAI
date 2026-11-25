"""Source Integrity Agent: compare a reference's metadata with authoritative records.

Five fields are compared (title, authors, year, DOI, journal), each with its own
tolerance, and every comparison keeps both values and the reason so the student can see
exactly why a status was given. A failed lookup is never turned into "verified".
"""
import re
from difflib import SequenceMatcher

from . import scholarly
from .text import fold, norm_key, parse_person_name, similarity

FIELDS = ("title", "authors", "year", "doi", "journal")
STATUS_VERIFIED, STATUS_PARTIAL, STATUS_MISMATCH = "Verified match", "Partial match", "Mismatch"
STATUS_NOT_FOUND, STATUS_PENDING = "Not found", "Pending review"


def _parts(author) -> tuple[str, str]:
    """(given, family) for a dict author or a plain "Given Family" / "Family, Given" string."""
    if isinstance(author, dict):
        if author.get("family"):
            return author.get("given") or "", author["family"]
        return parse_person_name(author.get("name") or "")
    return parse_person_name(str(author))


def name_profile(author) -> dict:
    """Everything needed to compare two author names regardless of name order or hyphenation."""
    given, family = _parts(author)
    pieces = re.split(r"[\s\-\u2010-\u2015]+", f"{given} {family}")
    toks = {norm_key(x) for x in pieces if len(norm_key(x)) >= 2}
    fam_keys = {norm_key(family)} | {norm_key(x) for x in re.split(r"[\s\-]+", family) if len(norm_key(x)) >= 3}
    return {"tokens": toks | {norm_key(family)}, "family": {k for k in fam_keys if k},
            "full": norm_key(given + family), "label": f"{given} {family}".strip()}


def same_person(a: dict, b: dict) -> bool:
    if a["full"] and a["full"] == b["full"]:
        return True
    return bool(a["family"] & b["tokens"]) or bool(b["family"] & a["tokens"])


def author_text(authors) -> str:
    names = []
    for a in authors or []:
        if isinstance(a, dict):
            names.append(" ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name", ""))
        else:
            names.append(str(a))
    return "; ".join(n for n in names if n)


def _field(status, supplied, database, note=""):
    return {"status": status, "supplied": supplied, "database": database, "note": note}


def _title_tokens(value: str) -> list[str]:
    """Words of a title, ignoring case, accents, punctuation, hyphenation and markup."""
    return re.findall(r"[a-z0-9]+", fold(value))


def _word_changes(a: list[str], b: list[str]) -> tuple[list[str], float]:
    """Plain-language list of the words that differ (yours -> database) and the word-level similarity."""
    sm = SequenceMatcher(None, a, b, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace":
            out.append(f"“{' '.join(a[i1:i2])}” (yours) vs “{' '.join(b[j1:j2])}” (record)")
        elif tag == "delete":
            out.append(f"“{' '.join(a[i1:i2])}” only in your title")
        elif tag == "insert":
            out.append(f"“{' '.join(b[j1:j2])}” only in the record")
    return out, sm.ratio()


def compare_title(supplied: str, database: str) -> dict:
    """A title matches only when every word is the same. Case, punctuation, hyphens, accents and markup are
    ignored, but a changed, added or removed word is never "close enough": it is a Partial match that names
    the words, or a Mismatch when the titles are mostly different. (A similarity score would let
    "knowledge sharing" become "knowledge hiding" pass on a long title.)"""
    if not supplied:
        return _field("missing_supplied", supplied, database, "Your reference has no title.")
    if not database:
        return _field("missing_database", supplied, database, "The database record has no title.")
    a, b = _title_tokens(supplied), _title_tokens(database)
    if a == b:
        return _field("match", supplied, database, "Same words (case, punctuation and markup ignored).")
    main_a = _title_tokens(fold(supplied).split(":")[0])
    main_b = _title_tokens(fold(database).split(":")[0])
    changes, ratio = _word_changes(a, b)
    detail = "; ".join(changes[:4]) + (f"; and {len(changes) - 4} more" if len(changes) > 4 else "")
    if len(main_a) >= 3 and main_a == main_b:
        if ":" not in fold(supplied) or ":" not in fold(database):
            return _field("partial", supplied, database, "Main title matches; the subtitle is missing on one side.")
        return _field("partial", supplied, database, f"Main title matches; the subtitle differs: {detail}.")
    if ratio < 0.6:
        return _field("mismatch", supplied, database, f"Titles are mostly different: {detail}.")
    return _field("partial", supplied, database, f"Some words differ: {detail}.")


def compare_authors(supplied, database) -> dict:
    s = [name_profile(a) for a in supplied or [] if _parts(a)[1]]
    d = [name_profile(a) for a in database or [] if _parts(a)[1]]
    st, dt = author_text(supplied), author_text(database)
    if not s:
        return _field("missing_supplied", st, dt, "Your reference lists no authors.")
    if not d:
        return _field("missing_database", st, dt, "The database record lists no authors.")
    # One-to-one pairing of supplied authors with record authors.
    used, pairs = set(), []
    for i, a in enumerate(s):
        j = next((j for j, b in enumerate(d) if j not in used and same_person(a, b)), None)
        if j is not None:
            used.add(j)
            pairs.append((i, j))
    matched = len(pairs)
    overlap = matched / max(len(s), len(d))
    first = same_person(s[0], d[0])
    in_order = all(i == j for i, j in pairs)
    missing = [d[j]["label"] for j in range(len(d)) if j not in used][:3]
    if matched == len(s) == len(d) and in_order:
        return _field("match", st, dt, "Same authors in the same order (name order and initials ignored).")
    if matched == len(s) == len(d):
        return _field("partial", st, dt, "Same authors, but in a different order.")
    if matched == len(s) and first:
        return _field("partial", st, dt, f"Your list has {len(s)} of the {len(d)} authors in the record"
                      + (f" (missing {', '.join(missing)})" if missing else "") + ".")
    if overlap >= 0.5 or first:
        return _field("partial", st, dt, f"Only {matched} of {max(len(s), len(d))} authors agree"
                      + (f"; record also lists {', '.join(missing)}" if missing else "") + ".")
    return _field("mismatch", st, dt, f"Authors conflict ({matched} of {max(len(s), len(d))} agree, different first author).")


def compare_year(supplied: str, record_years: list[str], database: str) -> dict:
    years = [y for y in record_years if y] or ([database] if database else [])
    shown = " / ".join(years)
    if not supplied:
        return _field("missing_supplied", supplied, shown, "Your reference has no year.")
    if not years:
        return _field("missing_database", supplied, shown, "The database record has no year.")
    if supplied in years:
        note = "Year matches." if len(set(years)) == 1 else f"Year matches one of the dates in the record ({shown}: online vs issue date)."
        return _field("match", supplied, shown, note)
    try:
        close = any(abs(int(supplied) - int(y)) == 1 for y in years)
    except ValueError:
        close = False
    if close:
        return _field("partial", supplied, shown, "Off by one year; often an online-first vs print-issue date. Check the version you cite.")
    return _field("mismatch", supplied, shown, "Year conflicts with the database record.")


def compare_doi(supplied: str, database: str) -> dict:
    s, d = scholarly.clean_doi(supplied), scholarly.clean_doi(database)
    if not s and not d:
        return _field("missing_both", s, d, "No DOI in your reference or the record (some works have none).")
    if not s:
        return _field("missing_supplied", s, d, "Your reference has no DOI; the record lists one.")
    if not d:
        return _field("missing_database", s, d, "The record does not list a DOI.")
    if s == d:
        return _field("match", s, d, "DOI identical.")
    return _field("mismatch", s, d, "DOI differs from the record.")


_VENUE_NOISE = {"proceedings", "proceeding", "of", "the", "on", "in", "and", "ieee", "acm", "annual", "international",
                "conference", "conf", "symposium", "workshop", "meeting", "joint", "th", "st", "nd", "rd"}


def venue_core(name: str) -> frozenset:
    """A conference name without years, ordinals, "Proceedings of the" and publisher words."""
    words = re.sub(r"\d+(st|nd|rd|th)?", " ", fold(name)).replace("-", " ").split()
    return frozenset(w.strip("().,:;&") for w in words if w.strip("().,:;&") and w.strip("().,:;&") not in _VENUE_NOISE)


def compare_journal(supplied: str, database: str, supplied_issn=None, record_issn=None, conference: bool = False) -> dict:
    if not supplied:
        return _field("missing_supplied", supplied, database, "Your reference has no journal/venue.")
    if not database:
        return _field("missing_database", supplied, database, "The record has no journal/venue.")
    if supplied_issn and record_issn and set(map(str.upper, supplied_issn)) & set(map(str.upper, record_issn)):
        return _field("match", supplied, database, "Same ISSN.")
    sim = similarity(supplied, database)
    a, b = norm_key(supplied), norm_key(database)
    if conference:
        # Crossref and OpenAlex name the same conference differently ("2022 IEEE ... (ICCSI)").
        ca, cb = venue_core(supplied), venue_core(database)
        if ca and cb and (ca <= cb or cb <= ca) and len(ca & cb) >= 2:
            return _field("match", supplied, database, "Same conference once years, ordinals and publisher words are ignored.")
    if sim >= 0.9 or a == b:
        return _field("match", supplied, database, f"Venue similarity {sim:.2f}.")
    if a in b or b in a or sim >= 0.6:
        return _field("partial", supplied, database, "Venue name differs (abbreviation or variant?).")
    return _field("mismatch", supplied, database, f"Venue differs (similarity {sim:.2f}).")


def compare(ref: dict, rec: dict) -> dict:
    return {
        "title": compare_title(ref.get("title", ""), rec.get("title", "")),
        "authors": compare_authors(ref.get("authors"), rec.get("authors")),
        "year": compare_year(str(ref.get("year") or ""), rec.get("years") or [], str(rec.get("year") or "")),
        "doi": compare_doi(ref.get("doi", ""), rec.get("doi", "")),
        "journal": compare_journal(ref.get("journal", ""), rec.get("journal", ""), ref.get("issn"), rec.get("issn"),
                                   conference="conference-paper" in (ref.get("kind"), rec.get("kind"))),
    }


def overall(fields: dict) -> tuple[str, str]:
    mism = [k for k, v in fields.items() if v["status"] == "mismatch"]
    part = [k for k, v in fields.items() if v["status"] == "partial"]
    missing = [k for k, v in fields.items() if v["status"] in ("missing_supplied", "missing_database")]
    if mism:
        return STATUS_MISMATCH, "Conflicting fields: " + ", ".join(mism) + ". Values were not changed; review them side by side."
    if part or missing:
        bits = []
        if part:
            bits.append("needs review: " + ", ".join(part))
        if missing:
            bits.append("missing: " + ", ".join(missing))
        return STATUS_PARTIAL, "Some fields match; " + "; ".join(bits) + "."
    return STATUS_VERIFIED, "Title, authors, year, DOI and journal agree with the database record."


def _merge_years(primary: dict, other: dict | None) -> dict:
    if other:
        primary = {**primary, "years": list(dict.fromkeys((primary.get("years") or []) + (other.get("years") or [])))}
    return primary


def run(ref: dict) -> dict:
    """Look the reference up and return a verification result (not yet saved)."""
    searched, errors, records = [], [], {}
    doi = scholarly.clean_doi(ref.get("doi", ""))
    if doi:
        for name, fn in (("Crossref", scholarly.crossref_by_doi), ("OpenAlex", scholarly.openalex_by_doi)):
            searched.append(f"{name} (DOI lookup)")
            try:
                records[name] = fn(doi)
            except scholarly.NotFound:
                pass
            except scholarly.ServiceError as e:
                errors.append(str(e))
    else:
        query = " ".join(filter(None, [ref.get("title", ""), author_text(ref.get("authors"))[:120], str(ref.get("year") or "")]))
        for name, fn, arg in (("Crossref", scholarly.crossref_bibliographic, query),
                              ("OpenAlex", scholarly.openalex_title_search, ref.get("title", ""))):
            searched.append(f"{name} (title search)")
            try:
                cands = fn(arg)
            except scholarly.ServiceError as e:
                errors.append(str(e))
                continue
            best = max(cands, key=lambda c: similarity(c["title"], ref.get("title", "")), default=None)
            if best and similarity(best["title"], ref.get("title", "")) >= 0.80:
                records[name] = best

    if not records:
        if errors:
            return {"status": STATUS_PENDING, "reason": "Lookup incomplete: " + "; ".join(errors) + ". Retry later or review manually.",
                    "fields": {}, "searched": searched, "record": None, "suggestions": {}}
        where = " and ".join(s.split(" (")[0] for s in searched)
        return {"status": STATUS_NOT_FOUND,
                "reason": f"No matching record in the databases searched ({where}). This does not prove the work does not exist; check the details or add a DOI.",
                "fields": {}, "searched": searched, "record": None, "suggestions": {}}

    primary_name = "Crossref" if "Crossref" in records else "OpenAlex"
    other_name = "OpenAlex" if primary_name == "Crossref" else "Crossref"
    primary = _merge_years(records[primary_name], records.get(other_name))
    fields = compare(ref, primary)
    status, reason = overall(fields)

    notes = []
    if len(records) == 2:
        a, b = records["Crossref"], records["OpenAlex"]
        if similarity(a["title"], b["title"]) < 0.9:
            notes.append("Crossref and OpenAlex titles differ")
        if a.get("year") and b.get("year") and a["year"] != b["year"]:
            notes.append(f"Crossref year {a['year']} vs OpenAlex year {b['year']}")
    if notes:
        reason += " Databases disagree: " + "; ".join(notes) + "."
    if errors:
        reason += " Note: " + "; ".join(errors) + "."
    reason = f"Compared with {primary_name}" + (f" (cross-checked with {other_name})" if other_name in records else "") + ". " + reason

    suggestions = {k: v["database"] for k, v in fields.items()
                   if v["status"] in ("mismatch", "partial", "missing_supplied") and v["database"]}
    if "authors" in suggestions:
        suggestions["authors"] = primary.get("authors")
    if "year" in suggestions:
        suggestions["year"] = primary.get("year") or (primary.get("years") or [""])[0]
    for extra in ("volume", "issue", "pages"):
        if primary.get(extra) and not ref.get(extra):
            suggestions[extra] = primary[extra]
    return {"status": status, "reason": reason, "fields": fields, "searched": searched,
            "record": {"provider": primary_name, **{k: primary.get(k) for k in
                       ("title", "authors", "year", "years", "doi", "journal", "issn", "volume", "issue", "pages", "url", "external_id", "kind")}},
            "suggestions": suggestions}
