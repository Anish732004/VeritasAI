"""Discovery Agent: concept-driven, filtered and explainable literature search.

Stages (each one is reported back to the student):
 1. Build a boolean query from the approved concept groups (required groups are ANDed).
 2. Query OpenAlex with hard filters: journal articles (and, if chosen, peer-reviewed conference
    papers), not retracted, language, date window.
 3. Look up each journal's citation metrics and assign a venue tier (or use a loaded journal list).
 4. Drop papers below the chosen tier and papers whose title/abstract miss a required concept.
 5. Score: concept coverage, text relevance, venue tier and recency, with a "why it matched" line.
"""
import csv
import json
from datetime import date

from . import ai, scholarly
from .config import CONFERENCE_LIST_PATH, JOURNAL_LIST_PATH
from .text import BM25, fold, phrase_in, tokens
from .verify import venue_core

WEIGHTS = {"coverage": 0.40, "text": 0.25, "venue": 0.20, "recency": 0.15}
TIER_ORDER = {"A": 3, "B": 2, "C": 1, "Unrated": 0}
TIER_VALUE = {"A": 1.0, "B": 0.7, "C": 0.35, "Unrated": 0.5}


def _quote(term: str) -> str:
    term = term.replace('"', "").strip()
    return f'"{term}"' if " " in term or "-" in term else term


def build_query(groups: list[dict], drop: int = 0) -> str:
    """("a" OR "b") AND ("c" OR "d") from required groups; `drop` removes the last N required groups."""
    required = [g for g in groups if g.get("required")] or groups[:1]
    if drop:
        required = required[: max(1, len(required) - drop)]
    parts = ["(" + " OR ".join(_quote(t) for t in g["terms"][:10]) + ")" for g in required]
    return " AND ".join(parts)


def load_journal_list() -> dict[str, dict]:
    """Optional data/journal_list.csv with columns: issn,name,list,tier (tier is A, B or C)."""
    if not JOURNAL_LIST_PATH.exists():
        return {}
    out = {}
    with JOURNAL_LIST_PATH.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            issn = (r.get("issn") or "").strip().upper()
            if issn and (r.get("tier") or "").strip().upper() in TIER_VALUE:
                out[issn] = {"list": (r.get("list") or "Journal list").strip(), "tier": r["tier"].strip().upper(),
                             "name": (r.get("name") or "").strip()}
    return out


def load_conference_list() -> list[dict]:
    """Optional data/conference_list.csv with columns: name,list,tier (e.g. CORE rank A*, A, B, C).

    A* counts as A. Names are matched after ignoring years, ordinals and words such as
    "Proceedings of the" or "International Conference on", so "2022 IEEE Conf. on X" matches "X".
    """
    if not CONFERENCE_LIST_PATH.exists():
        return []
    out = []
    with CONFERENCE_LIST_PATH.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            tier = (r.get("tier") or "").strip().upper().replace("*", "")
            core = venue_core(r.get("name") or "")
            if core and tier in TIER_VALUE:
                out.append({"core": core, "tier": tier, "list": (r.get("list") or "Conference list").strip(),
                            "name": (r.get("name") or "").strip(), "rank": (r.get("tier") or "").strip()})
    return out


# Series that publish the proceedings of many unrelated conferences. Their quality depends on the
# individual conference (some are rigorous, some publish almost everything), so they are capped at C.
PROCEEDINGS_SERIES = ("web of conferences", "conference series", "aip conference proceedings",
                      "lecture notes in", "advances in intelligent systems and computing", "communications in computer and information science")


# Societies and publishers whose conference proceedings are peer reviewed and indexed. This shows that a
# conference sits in a recognised proceedings programme, not that every paper in it is strong.
RECOGNISED_PUBLISHERS = (
    "institute of electrical and electronics engineers", "association for computing machinery",
    "institution of engineering and technology", "association for the advancement of artificial intelligence",
    "association for computational linguistics", "american society of mechanical engineers", "springer",
    "elsevier", "wiley", "siam", "usenix", "spie", "optica", "ifac", "american institute of aeronautics")


def is_conference(work: dict) -> bool:
    return work.get("kind") == "conference-paper"


def conference_tier(work: dict, source: dict | None, conference_list: list[dict]) -> dict:
    venue = work.get("journal") or ""
    core = venue_core(venue)
    for hit in conference_list:
        if core and (core == hit["core"] or (len(hit["core"]) >= 2 and hit["core"] <= core)):
            return {"tier": hit["tier"], "basis": f"{hit['list']} {hit['rank']}: {hit['name']}", "list": hit["list"], "conference": True}
    stats = (source or {}).get("summary_stats") or {}
    citedness, h = stats.get("2yr_mean_citedness"), stats.get("h_index")
    series = any(s in venue.lower() for s in PROCEEDINGS_SERIES) or (source or {}).get("type") == "book series"
    if series:
        return {"tier": "C", "basis": "Proceedings series that publishes many different conferences. "
                "Judge the individual conference; the series name alone is not a quality signal.", "conference": True}
    if citedness is None:
        return {"tier": "Unrated", "basis": "No conference metrics available", "conference": True}
    h = h or 0
    publisher = ((source or {}).get("host_organization_name") or "").lower()
    recognised = any(p in publisher for p in RECOGNISED_PUBLISHERS)
    base = f"conference series h-index {h}, 2-yr mean citedness {citedness:.2f}"
    if h >= 60 and citedness >= 1:
        tier, why = "A", base
    elif h >= 30 and citedness >= 1:
        tier, why = "B", base
    elif recognised and h >= 10:
        tier, why = "B", f"{(source or {}).get('host_organization_name')} proceedings, {base}; selectivity varies by conference"
    else:
        tier, why = "C", base + ("" if recognised else "; publisher not on the recognised list")
    return {"tier": tier, "basis": why[:1].upper() + why[1:] + " (no ranked conference list loaded)" if not conference_list
            else why[:1].upper() + why[1:] + " (not on your conference list)",
            "citedness": citedness, "h_index": h, "conference": True}


def venue_tier(work: dict, sources: dict, journal_list: dict, conference_list: list[dict] | None = None) -> dict:
    if is_conference(work):
        return conference_tier(work, sources.get(work.get("source_id") or ""), conference_list or [])
    for issn in work.get("issn") or []:
        hit = journal_list.get(issn.upper())
        if hit:
            return {"tier": hit["tier"], "basis": f"{hit['list']} {hit['tier']}", "list": hit["list"]}
    src = sources.get(work.get("source_id") or "")
    stats = (src or {}).get("summary_stats") or {}
    citedness = stats.get("2yr_mean_citedness")
    h = stats.get("h_index")
    if citedness is None:
        return {"tier": "Unrated", "basis": "No journal metrics available"}
    h = h or 0
    tier = "A" if citedness >= 3 and h >= 30 else "B" if citedness >= 1 and h >= 15 else "C"
    return {"tier": tier, "basis": f"Journal 2-yr mean citedness {citedness:.2f}, h-index {h}",
            "citedness": citedness, "h_index": h}


def concept_hits(work: dict, groups: list[dict]) -> list[dict]:
    title_t = tokens(work["title"], drop_stopwords=False)
    abs_t = tokens(work.get("abstract") or "", drop_stopwords=False)
    out = []
    for g in groups:
        in_title = [t for t in g["terms"] if phrase_in(t, title_t)]
        in_abs = [t for t in g["terms"] if phrase_in(t, abs_t)]
        out.append({"label": g["label"], "required": bool(g.get("required")),
                    "where": "title" if in_title else "abstract" if in_abs else None,
                    "terms": list(dict.fromkeys(in_title + in_abs))[:4]})
    return out


def recency(work: dict, years: int) -> float:
    try:
        y = int(work.get("year") or 0)
    except ValueError:
        return 0.0
    age = max(0, date.today().year - y)
    return max(0.0, 1 - age / max(1, years))


def score(work: dict, hits: list[dict], text_score: float, tier: dict, years: int) -> dict:
    weight = {True: 1.0, False: 0.5}
    total = sum(weight[h["required"]] for h in hits) or 1
    covered = sum(weight[h["required"]] * (1.0 if h["where"] == "title" else 0.75 if h["where"] else 0) for h in hits)
    parts = {
        "coverage": covered / total,
        "text": text_score,
        "venue": TIER_VALUE[tier["tier"]],
        "recency": recency(work, years),
    }
    parts = {k: round(v, 3) for k, v in parts.items()}
    return {"total": round(sum(WEIGHTS[k] * v for k, v in parts.items()), 3), "parts": parts}


def explain(hits: list[dict], tier: dict, work: dict) -> str:
    matched = [f"{h['label']} ({h['where']})" for h in hits if h["where"]]
    bits = ["Matches " + ", ".join(matched)] if matched else []
    bits.append(("conference paper, " if work.get("kind") == "conference-paper" else "") + f"venue tier {tier['tier']}: {tier['basis']}")
    bits.append(str(work.get("year") or "year unknown"))
    if not work.get("abstract"):
        bits.append("no abstract available, matched on title only")
    return " · ".join(bits)


def discover(plan: dict, existing_dois: set[str], existing_titles: set[str]) -> dict:
    groups = plan.get("concept_groups") or []
    if not groups:
        raise ValueError("The plan has no concept groups to search with.")
    f = {**{"years": 5, "language": "en", "min_tier": "B", "article_only": True, "include_conferences": True,
            "include_foundational": False}, **(plan.get("filters") or {})}
    years = max(1, min(30, int(f.get("years") or 5)))
    from_date = date(date.today().year - years, date.today().month, 1).isoformat()
    filters = ["is_retracted:false", f"from_publication_date:{from_date}"]
    if f.get("article_only", True):
        if f.get("include_conferences", True):
            filters += ["type:article|conference-paper", "primary_location.source.type:journal|conference"]
        else:
            filters += ["type:article", "primary_location.source.type:journal"]
    if f.get("language"):
        filters.append(f"language:{f['language']}")

    report = {"queries": [], "filters": filters, "relaxed": None}
    query = build_query(groups)
    works, count = scholarly.openalex_search(query, filters, per_page=50)
    report["queries"].append({"query": query, "count": count})
    # Many required concepts can leave too few papers. Relax from the end of the list (the plan lists the most
    # essential concepts first), one concept at a time, until there are enough candidates. A relaxed concept
    # becomes optional: it still raises the ranking, but a paper is no longer dropped for missing it.
    required = [g for g in groups if g.get("required")] or groups[:1]
    relaxed: list[str] = []
    seen = {w["external_id"] for w in works}
    for drop in range(1, len(required)):
        if len(works) >= 8:
            break
        query_n = build_query(groups, drop=drop)
        more, count_n = scholarly.openalex_search(query_n, filters, per_page=50)
        report["queries"].append({"query": query_n, "count": count_n})
        relaxed = [g["label"] for g in required[len(required) - drop:]]
        works += [w for w in more if w["external_id"] not in seen]
        seen |= {w["external_id"] for w in more}
    if relaxed:
        report["relaxed"] = (f"Only {len(works)} papers matched all {len(required)} required concepts, so "
                             + ", ".join(relaxed) + (" was" if len(relaxed) == 1 else " were")
                             + " made optional: papers are no longer dropped for missing "
                             + ("it" if len(relaxed) == 1 else "them") + ", but they rank lower.")
    effective = [{**g, "required": g.get("required") and g["label"] not in relaxed} if g.get("required") else g
                 for g in groups]
    if not any(g.get("required") for g in effective):
        effective = groups

    foundational = []
    if f.get("include_foundational"):
        old_filters = [x for x in filters if not x.startswith("from_publication_date")]
        old_filters.append(f"to_publication_date:{from_date}")
        foundational, _ = scholarly.openalex_search(query, old_filters, per_page=5, sort="cited_by_count:desc")
        for w in foundational:
            w["foundational"] = True

    pool = works + foundational
    try:
        sources = scholarly.openalex_sources([w.get("source_id") for w in pool])
    except scholarly.ServiceError:
        sources = {}
        report["venue_warning"] = "Journal metrics could not be retrieved; venue tiers are marked Unrated."
    journal_list = load_journal_list()
    conference_list = load_conference_list()

    docs = [tokens(w["title"] + " " + w["title"] + " " + (w.get("abstract") or "")) for w in pool]
    bm = BM25(docs)
    q_tokens = [t for g in groups for term in g["terms"] for t in tokens(term)]
    raw = [bm.score(q_tokens, i) for i in range(len(pool))]
    top = max(raw) if raw else 1

    min_rank = TIER_ORDER.get(str(f.get("min_tier") or "C").upper(), 1)
    removed = {"below venue tier": 0, "missing a required concept": 0, "already in project": 0}
    results = []
    for i, w in enumerate(pool):
        tier = venue_tier(w, sources, journal_list, conference_list)
        hits = concept_hits(w, effective)
        key_doi = w.get("doi")
        if (key_doi and key_doi in existing_dois) or w["title"].lower() in existing_titles:
            removed["already in project"] += 1
            continue
        if any(h["required"] and not h["where"] for h in hits) and not w.get("foundational"):
            removed["missing a required concept"] += 1
            continue
        if TIER_ORDER[tier["tier"]] < min_rank and tier["tier"] != "Unrated":
            removed["below venue tier"] += 1
            continue
        s = score(w, hits, (raw[i] / top) if top else 0, tier, years)
        w.update({"venue": tier, "concepts": hits, "score": s, "why": explain(hits, tier, w)})
        results.append(w)
    results.sort(key=lambda w: (not w.get("foundational"), w["score"]["total"]), reverse=True)
    results = [w for w in results if not w.get("foundational")][:20] + [w for w in results if w.get("foundational")][:5]

    report.update({
        "retrieved": len(pool),
        "shown": len(results),
        "removed": removed,
        "window": f"Published since {from_date}",
        "conference_papers": len([r for r in results if is_conference(r)]),
        "conference_list": bool(conference_list),
        "min_tier": str(f.get("min_tier") or "C").upper(),
        "note": ("Results come from OpenAlex only; they are candidate sources, not evidence for any claim. "
                 "Venue tiers use journal or conference citation metrics (or your journal and conference lists) and are a "
                 "screening aid, not a judgement of an individual paper. Check how a conference reviewed its papers "
                 "(full papers or abstracts only)."),
    })
    if len([r for r in results if not r.get("foundational")]) < 5:
        report["too_few"] = ("Fewer than 5 papers passed. Consider widening the time window, lowering the "
                             "venue tier or making a concept group optional. Nothing was added to fill the list.")
    return {"results": results, "report": report}


# ---------------------------------------------------------------- AI relevance check

RELEVANCE_LABELS = {3: "Directly relevant", 2: "Relevant", 1: "Tangential", 0: "Likely off-topic"}
RELEVANCE_TASK = (
    "You are screening literature-search results for a university student. For each paper decide how well it helps "
    "answer the student's research question, using ONLY the title and abstract given. Levels: 3 = directly addresses "
    "the question's main concepts in the question's setting; 2 = relevant: covers the key concepts but in a narrower, "
    "broader or neighbouring setting; 1 = tangential: shares keywords but is mainly about something else; 0 = off-topic "
    "(for example a word used in a different sense). Be strict: sharing a keyword is not relevance. If there is no "
    "abstract, judge from the title alone and use at most level 2. For each paper return an object with keys "
    "i (the number given), level (0-3), reason (one short sentence in your own words saying what the paper is about "
    "and how it relates to the question) and quote (one sentence copied exactly from the title or abstract that "
    "supports your level, or an empty string). Return a JSON list with one object per paper. Never invent details."
)
MAX_RATED = 30


def apply_ai_relevance(results: list[dict], data, model: str = "") -> int:
    """Attach the model's ratings to the results and re-rank them. Pure function (see tests).

    The model only rates and explains. Papers are never removed: "likely off-topic" ones sink to the bottom
    of their group and say so. A quote is shown only if it really appears in the title or abstract, and a
    paper without an abstract can be rated at most "Relevant". Returns how many papers were rated.
    """
    rated = 0
    for d in data if isinstance(data, list) else []:
        if not isinstance(d, dict):
            continue
        try:
            r = results[int(d.get("i"))]
            level = int(d.get("level"))
        except (TypeError, ValueError, IndexError):
            continue
        if level not in RELEVANCE_LABELS or isinstance(d.get("level"), bool):
            continue
        if not r.get("abstract"):
            level = min(level, 2)
        text = fold((r.get("title") or "") + " " + (r.get("abstract") or ""))
        quote = str(d.get("quote") or "").strip()
        grounded = bool(quote) and fold(quote)[:80] in text
        r["ai_relevance"] = {"level": level, "label": RELEVANCE_LABELS[level], "reason": str(d.get("reason") or "").strip()[:300],
                             "quote": quote[:400] if grounded else "", "model": model}
        rated += 1
    for r in results:
        base = r["score"]["total"]
        level = (r.get("ai_relevance") or {}).get("level")
        if level is not None:
            r["score"]["parts"]["ai"] = round(level / 3, 3)
            r["score"]["total"] = round(0.5 * base + 0.5 * (level / 3), 3)
    # Re-rank within each group (recent papers, then foundational ones), keeping the group order.
    main = sorted([r for r in results if not r.get("foundational")], key=lambda r: r["score"]["total"], reverse=True)
    old = sorted([r for r in results if r.get("foundational")], key=lambda r: r["score"]["total"], reverse=True)
    results[:] = main + old
    return rated


def ai_relevance(question: str, plan: dict, results: list[dict]) -> dict:
    """Ask the model to rate how relevant each result is to the research question (needs AI turned on)."""
    batch = results[:MAX_RATED]
    if not batch:
        return {"rated": 0, "model": None}
    note = (plan.get("ai_note") or "").strip()
    required = "; ".join(g["label"] for g in plan.get("concept_groups") or [] if g.get("required"))
    context = "Research question: " + question + (f"\nHow it was understood: {note}" if note else "") + \
              (f"\nConcepts papers should cover: {required}" if required else "")
    papers = [{"i": i, "title": r["title"], "year": r.get("year"), "venue": r.get("journal"),
               "abstract": (r.get("abstract") or "")[:1000]} for i, r in enumerate(batch)]
    data, meta = ai.complete_json(RELEVANCE_TASK, context, data=json.dumps(papers), max_tokens=3000,
                                  inputs=[r.get("external_id", "") for r in batch])
    rated = apply_ai_relevance(batch, data, meta.get("model", ""))
    results[:] = sorted([r for r in results if not r.get("foundational")], key=lambda r: r["score"]["total"], reverse=True) + \
                 sorted([r for r in results if r.get("foundational")], key=lambda r: r["score"]["total"], reverse=True)
    return {"rated": rated, "model": meta.get("model"), "meta": meta, "off_topic": len([r for r in results if (r.get("ai_relevance") or {}).get("level") == 0])}
