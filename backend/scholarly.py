"""Clients for OpenAlex (discovery + cross-check) and Crossref (DOI registry).

All calls go through `fetch_json`, which identifies the app, retries transient failures
with increasing waits, and caches responses for a day so repeated demos stay fast and
within the services' rate limits.
"""
import hashlib
import json
import time

import httpx

from . import db
from .config import CACHE_TTL_SECONDS, CONTACT_EMAIL, HTTP_TIMEOUT, OPENALEX_API_KEY
from .text import fold, reconstruct_abstract, strip_tags

OPENALEX = "https://api.openalex.org"
CROSSREF = "https://api.crossref.org"
USER_AGENT = "VERITAS-AI/2.0 (university research-integrity prototype" + (
    f"; mailto:{CONTACT_EMAIL})" if CONTACT_EMAIL else ")"
)

WORK_FIELDS = (
    "id,doi,display_name,publication_year,publication_date,authorships,primary_location,"
    "abstract_inverted_index,relevance_score,cited_by_count,type,language,is_retracted,biblio,"
    "open_access,best_oa_location"
)


class ServiceError(Exception):
    """A scholarly service could not answer (network, rate limit, server error)."""

    def __init__(self, service: str, message: str, status: int | None = None):
        super().__init__(f"{service}: {message}")
        self.service, self.status = service, status


class NotFound(Exception):
    pass


def _service(url: str) -> str:
    return "OpenAlex" if "openalex" in url else "Crossref" if "crossref" in url else "remote service"


def fetch_json(url: str, params: dict | None = None, *, use_cache: bool = True, retries: int = 3) -> dict:
    params = dict(params or {})
    if "openalex.org" in url:
        if OPENALEX_API_KEY:
            params["api_key"] = OPENALEX_API_KEY
        if CONTACT_EMAIL:
            params["mailto"] = CONTACT_EMAIL
    key = hashlib.sha1((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    if use_cache:
        with db.db() as con:
            hit = con.execute("SELECT value, fetched_at FROM api_cache WHERE key = ?", (key,)).fetchone()
        if hit and time.time() - hit["fetched_at"] < CACHE_TTL_SECONDS:
            cached = json.loads(hit["value"])
            if cached.get("__not_found__"):
                raise NotFound(url)
            return cached

    service = _service(url)
    last = None
    for attempt in range(retries):
        try:
            r = httpx.get(url, params=params, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT},
                          follow_redirects=True)
        except httpx.HTTPError as e:
            last = ServiceError(service, f"network error ({type(e).__name__})")
        else:
            if r.status_code == 404:
                with db.db() as con:
                    con.execute("INSERT OR REPLACE INTO api_cache VALUES (?, ?, ?)",
                                (key, json.dumps({"__not_found__": True}), time.time()))
                raise NotFound(url)
            if r.status_code == 200:
                data = r.json()
                with db.db() as con:
                    con.execute("INSERT OR REPLACE INTO api_cache VALUES (?, ?, ?)",
                                (key, json.dumps(data), time.time()))
                return data
            last = ServiceError(service, f"HTTP {r.status_code}", r.status_code)
            if r.status_code < 500 and r.status_code != 429:
                break
        time.sleep(0.6 * (2 ** attempt))
    raise last or ServiceError(service, "unknown error")


# ---------------------------------------------------------------- normalisation

def split_name(name: str) -> dict:
    name = strip_tags(name).strip()
    if "," in name:
        family, given = [p.strip() for p in name.split(",", 1)]
        return {"given": given, "family": family}
    parts = name.split()
    if len(parts) == 1:
        return {"given": "", "family": parts[0]}
    return {"given": " ".join(parts[:-1]), "family": parts[-1]}


def clean_doi(doi: str) -> str:
    doi = (doi or "").strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
    return doi.strip().lower()


def work_kind(type_: str, source_type: str = "") -> str:
    """"conference-paper" or "journal-article" (the two kinds VERITAS cites)."""
    t = (type_ or "").lower()
    if t in ("conference-paper", "proceedings-article") or (source_type == "conference" and t in ("", "article")):
        return "conference-paper"
    return "journal-article"


def from_openalex(w: dict) -> dict:
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    biblio = w.get("biblio") or {}
    pages = "-".join(p for p in (biblio.get("first_page"), biblio.get("last_page")) if p)
    oa = w.get("best_oa_location") or {}
    return {
        "provider": "OpenAlex",
        "external_id": (w.get("id") or "").rsplit("/", 1)[-1],
        "title": strip_tags(w.get("display_name") or w.get("title") or ""),
        "authors": [split_name((a.get("author") or {}).get("display_name") or "")
                    for a in w.get("authorships") or [] if (a.get("author") or {}).get("display_name")],
        "year": str(w.get("publication_year") or ""),
        "years": [str(w["publication_year"])] if w.get("publication_year") else [],
        "publication_date": w.get("publication_date") or "",
        "doi": clean_doi(w.get("doi") or ""),
        "journal": strip_tags(src.get("display_name") or ""),
        "issn": [i for i in (src.get("issn") or []) if i] or ([src["issn_l"]] if src.get("issn_l") else []),
        "source_id": (src.get("id") or "").rsplit("/", 1)[-1],
        "source_type": src.get("type") or "",
        "volume": biblio.get("volume") or "",
        "issue": biblio.get("issue") or "",
        "pages": pages,
        "url": w.get("doi") or loc.get("landing_page_url") or w.get("id") or "",
        "abstract": reconstruct_abstract(w.get("abstract_inverted_index")),
        "type": w.get("type") or "",
        "kind": work_kind(w.get("type") or "", src.get("type") or ""),
        "language": w.get("language") or "",
        "is_retracted": bool(w.get("is_retracted")),
        "cited_by_count": w.get("cited_by_count") or 0,
        "relevance_score": w.get("relevance_score"),
        "oa_url": oa.get("pdf_url") or oa.get("landing_page_url") or "",
    }


def _cr_year(parts) -> str:
    try:
        return str(parts["date-parts"][0][0] or "")
    except (KeyError, IndexError, TypeError):
        return ""


def from_crossref(m: dict) -> dict:
    years = []
    for key in ("published-print", "published-online", "issued", "published"):
        y = _cr_year(m.get(key) or {})
        if y and y not in years:
            years.append(y)
    title = strip_tags((m.get("title") or [""])[0])
    sub = strip_tags((m.get("subtitle") or [""])[0]) if m.get("subtitle") else ""
    if sub and sub.lower() not in title.lower():
        title = f"{title}: {sub}"
    return {
        "provider": "Crossref",
        "external_id": m.get("DOI", ""),
        "title": title,
        "authors": [{"given": a.get("given", ""), "family": a.get("family") or a.get("name", "")}
                    for a in m.get("author") or [] if a.get("family") or a.get("name")],
        "year": _cr_year(m.get("issued") or {}) or (years[0] if years else ""),
        "years": years,
        "doi": clean_doi(m.get("DOI", "")),
        "journal": strip_tags((m.get("container-title") or [""])[0]),
        "issn": m.get("ISSN") or [],
        "volume": m.get("volume", ""),
        "issue": m.get("issue", ""),
        "pages": m.get("page", ""),
        "url": m.get("URL", ""),
        "abstract": strip_tags(m.get("abstract") or ""),
        "type": m.get("type", ""),
        "kind": work_kind(m.get("type", "")),
    }


# ---------------------------------------------------------------- lookups

def openalex_by_doi(doi: str) -> dict:
    return from_openalex(fetch_json(f"{OPENALEX}/works/https://doi.org/{clean_doi(doi)}", {"select": WORK_FIELDS}))


def crossref_by_doi(doi: str) -> dict:
    return from_crossref(fetch_json(f"{CROSSREF}/works/{clean_doi(doi)}")["message"])


def crossref_bibliographic(query: str, rows: int = 5) -> list[dict]:
    data = fetch_json(f"{CROSSREF}/works", {"query.bibliographic": query, "rows": rows})
    return [from_crossref(m) for m in data["message"]["items"]]


def openalex_title_search(title: str, rows: int = 5) -> list[dict]:
    clean = fold(title).replace(",", " ").replace(":", " ")
    data = fetch_json(f"{OPENALEX}/works", {"filter": f"title.search:{clean}", "per-page": rows, "select": WORK_FIELDS})
    return [from_openalex(w) for w in data.get("results", [])]


def openalex_search(query: str, filters: list[str], per_page: int = 50, sort: str | None = None) -> tuple[list[dict], int]:
    params = {"search": query, "per-page": per_page, "select": WORK_FIELDS}
    if filters:
        params["filter"] = ",".join(filters)
    if sort:
        params["sort"] = sort
    data = fetch_json(f"{OPENALEX}/works", params)
    return [from_openalex(w) for w in data.get("results", [])], (data.get("meta") or {}).get("count", 0)


def openalex_sources(source_ids: list[str]) -> dict[str, dict]:
    ids = [s for s in dict.fromkeys(source_ids) if s]
    out = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i : i + 50]
        data = fetch_json(f"{OPENALEX}/sources", {
            "filter": "openalex:" + "|".join(chunk), "per-page": 50,
            "select": "id,display_name,issn_l,issn,summary_stats,is_in_doaj,type,host_organization_name",
        })
        for s in data.get("results", []):
            out[s["id"].rsplit("/", 1)[-1]] = s
    return out
