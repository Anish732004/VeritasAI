"""Offline tests for the parts of VERITAS that make judgements.

Run before every demo:  .venv/bin/python -m pytest -q
"""
import pytest

from backend import citations, concepts, evidence, redteam, verify

HUNG = {
    "title": "Inclusion in global virtual teams: Exploring non-spatial proximity and knowledge sharing on innovation",
    "authors": [{"given": "Shiu-Wan", "family": "Hung"}, {"given": "Min-Jhih", "family": "Cheng"},
                {"given": "Chen-En", "family": "Hou"}, {"given": "Nai-Rong", "family": "Chen"}],
    "year": "2021", "years": ["2021", "2020"], "doi": "10.1016/j.jbusres.2020.11.022",
    "journal": "Journal of Business Research", "issn": ["0148-2963"],
}


def ref(**kw):
    base = {k: v for k, v in HUNG.items() if k != "years"}
    base.update(kw)
    return base


# ---------------------------------------------------------------- verification

def test_exact_reference_is_verified():
    status, _ = verify.overall(verify.compare(ref(), HUNG))
    assert status == verify.STATUS_VERIFIED


def test_online_first_year_is_accepted():
    # The bug found in the original app: OpenAlex says 2020, Crossref issue year 2021.
    fields = verify.compare(ref(year="2020"), HUNG)
    assert fields["year"]["status"] == "match"
    assert verify.overall(fields)[0] == verify.STATUS_VERIFIED


def test_year_off_by_one_is_partial_not_mismatch():
    fields = verify.compare(ref(year="2022"), HUNG)
    assert fields["year"]["status"] == "partial"
    assert verify.overall(fields)[0] == verify.STATUS_PARTIAL


def test_wrong_year_on_a_real_paper_needs_a_fix_not_a_mismatch():
    """Phase 2 requirement 3: one wrong detail on a real paper is a small error the student can fix."""
    fields = verify.compare(ref(year="2015"), HUNG)
    status, reason = verify.overall(fields)
    assert fields["year"]["status"] == "mismatch" and status == verify.STATUS_PARTIAL
    assert "yours 2015" in reason and "2021" in reason


def test_wrong_authors_on_a_real_doi_is_a_mismatch():
    status, reason = verify.overall(verify.compare(ref(authors=[{"given": "G", "family": "Hinton"}]), HUNG))
    assert status == verify.STATUS_MISMATCH and "authors" in reason


def test_author_initials_and_hyphens_do_not_cause_mismatch():
    authors = [{"given": "S.", "family": "Hung"}, {"given": "M. J.", "family": "Cheng"},
               {"given": "C.", "family": "Hou"}, {"given": "N.", "family": "Chen"}]
    assert verify.compare(ref(authors=authors), HUNG)["authors"]["status"] == "match"


def test_author_string_form_and_order():
    swapped = ["Min-Jhih Cheng", "Shiu-Wan Hung", "Chen-En Hou", "Nai-Rong Chen"]
    assert verify.compare(ref(authors=swapped), HUNG)["authors"]["status"] == "partial"


def test_truncated_author_list_is_partial():
    assert verify.compare(ref(authors=HUNG["authors"][:2]), HUNG)["authors"]["status"] == "partial"


def test_wrong_authors_is_mismatch():
    assert verify.compare(ref(authors=["John Smith", "Jane Doe"]), HUNG)["authors"]["status"] == "mismatch"


def test_title_with_real_doi_is_caught():
    fields = verify.compare(ref(title="Deep learning for protein folding"), HUNG)
    assert fields["title"]["status"] == "mismatch"
    assert verify.overall(fields)[0] == verify.STATUS_MISMATCH


def test_missing_subtitle_is_partial():
    fields = verify.compare(ref(title="Inclusion in global virtual teams"), HUNG)
    assert fields["title"]["status"] == "partial"


def test_punctuation_and_case_do_not_matter():
    t = HUNG["title"].upper().replace(":", " -")
    assert verify.compare(ref(title=t), HUNG)["title"]["status"] == "match"


def test_missing_doi_is_partial_with_suggestion():
    fields = verify.compare(ref(doi=""), HUNG)
    assert fields["doi"]["status"] == "missing_supplied"
    assert verify.overall(fields)[0] == verify.STATUS_PARTIAL


def test_journal_abbreviation_is_partial_and_issn_matches():
    assert verify.compare(ref(journal="J Business Research", issn=[]), HUNG)["journal"]["status"] in ("partial", "match")
    assert verify.compare(ref(journal="JBR", issn=["0148-2963"]), HUNG)["journal"]["status"] == "match"


def test_wrong_journal_is_mismatch():
    assert verify.compare(ref(journal="Nature Physics", issn=[]), HUNG)["journal"]["status"] == "mismatch"


# ---------------------------------------------------------------- evidence

ABSTRACT = ("Personalised recommendations are widely used in online retail. Using a survey of 812 shoppers, we find "
            "that perceived relevance of recommendations is positively associated with satisfaction. However, the "
            "effect weakens when consumers report high privacy concern.")
FULLTEXT = ("[PDF page 1]\nIntroduction text that is long enough to count as a sentence here.\n\n[PDF page 4]\n"
            "Our results show that perceived rele-\nvance of recommendations is positively associated with satis-\n"
            "faction among frequent shoppers. Further sentences follow in the discussion section here.")


def test_exact_passage_in_abstract():
    loc = evidence.locate("perceived relevance of recommendations is positively associated with satisfaction", {"abstract": ABSTRACT})
    assert loc["match"] == "exact" and loc["location"] == "abstract"


def test_pdf_line_breaks_and_hyphenation_still_match_with_page():
    loc = evidence.locate("perceived relevance of recommendations is positively associated with satisfaction among frequent shoppers",
                          {"fulltext": FULLTEXT})
    assert loc["match"] == "exact"
    assert loc["location"] == "full text" and loc["page"] == 4


def test_near_match_tolerates_small_differences():
    loc = evidence.locate("Using a survey of 812 shoppers we found that perceived relevance of recommendations is positively associated with satisfaction",
                          {"abstract": ABSTRACT})
    assert loc["match"] == "near"


def test_invented_passage_is_not_located():
    loc = evidence.locate("AI personalisation doubled customer lifetime value in every market studied", {"abstract": ABSTRACT})
    assert loc["match"] == "not_located"


def test_no_text_is_reported_honestly():
    assert evidence.locate("anything at all that is long enough", {})["match"] == "no_text"


def test_suggestions_come_from_source_text_only():
    sugg = evidence.suggest("privacy concern weakens the effect of recommendations", {"abstract": ABSTRACT})
    assert sugg and all(s["text"] in ABSTRACT for s in sugg)
    assert "privacy concern" in sugg[0]["text"]


@pytest.mark.parametrize("ev,ctype,expected", [
    ([], "source_finding", evidence.NOT_FOUND),
    ([{"stance": "supports", "match": "exact", "location": "abstract", "reference_id": "r"}], "source_finding", evidence.SOURCE_SUPPORTED),
    ([{"stance": "supports", "match": "no_text", "reference_id": "r"}], "source_finding", evidence.REPORTED),
    ([{"stance": "supports", "match": "not_located", "reference_id": "r"}], "source_finding", evidence.NOT_FOUND),
    ([{"stance": "challenges", "match": "exact", "reference_id": "r"}], "source_finding", evidence.CONTRADICTED),
    ([{"stance": "supports", "match": "exact", "reference_id": "r"}], "ai_interpretation", evidence.AI_INTERPRETATION),
])
def test_claim_status_rules(ev, ctype, expected):
    status, reason, _ = evidence.claim_status({"claim_type": ctype}, ev, {"r": {"title": "T"}})
    assert status == expected and reason


def test_abstract_level_is_labelled():
    _, reason, level = evidence.claim_status({}, [{"stance": "supports", "match": "exact", "location": "abstract", "reference_id": "r"}], {})
    assert level == "abstract" and "Abstract-level" in reason


# ---------------------------------------------------------------- red team

def test_rule_checks_flag_overgeneralisation_and_missing_evidence():
    kinds = {a["kind"] for a in redteam.rule_checks({"text": "AI always increases retention"}, [], {})}
    assert {"Overgeneralisation", "Causal language", "Missing evidence"} <= kinds


def test_rule_stance():
    assert redteam.rule_stance("Personalisation did not improve satisfaction.") == "challenges"
    assert redteam.rule_stance("However, the effect depends on privacy concern.") == "qualifies"
    assert redteam.rule_stance("We surveyed 300 shoppers in India.") == "unclear"


# ---------------------------------------------------------------- planning

def test_concept_map_drops_question_words():
    groups = concepts.rule_based_groups("How can AI help manage liquidity risk in banks?")
    labels = [g["label"] for g in groups]
    assert labels[:2] == ["Artificial intelligence", "Liquidity risk"]
    assert [g["required"] for g in groups][:3] == [True, True, False]
    assert not any(l.lower() in ("how", "can", "help") for l in labels)


def test_spelling_variants():
    groups = concepts.rule_based_groups("personalisation and customer loyalty")
    terms = {t.lower() for g in groups for t in g["terms"]}
    assert {"personalisation", "personalization"} <= terms


# ---------------------------------------------------------------- citations

def cite_ref(**kw):
    r = {"id": "x", "title": "Does personalisation work?", "authors": [{"given": "Ann", "family": "Lee"}, {"given": "Bo", "family": "Kim"}],
         "year": "2024", "journal": "Journal of Retailing", "volume": "100", "issue": "2", "pages": "10-20", "doi": "10.1/abc"}
    r.update(kw)
    return r


def test_apa_has_no_double_punctuation_and_keeps_italics():
    e = citations.bibliography([cite_ref()], "APA 7")[0]
    assert "?." not in e["text"]
    assert "<i>Journal of Retailing</i>" in e["html"]
    assert e["text"].startswith("Lee, A., & Kim, B. (2024).")
    assert e["in_text"] == "(Lee & Kim, 2024)"


def test_bibliography_is_alphabetical():
    entries = citations.bibliography([cite_ref(id="b", authors=[{"family": "Zhou", "given": "Y"}]),
                                      cite_ref(id="a", authors=[{"family": "Adams", "given": "J"}])], "APA 7")
    assert [e["reference_id"] for e in entries] == ["a", "b"]


def test_engine_output_is_sanitised():
    e = citations.bibliography([cite_ref(title="<script>alert(1)</script> Real title")], "APA 7")[0]
    assert "<script" not in e["html"]


@pytest.mark.parametrize("style", list(citations.STYLES))
def test_all_styles_render(style):
    assert citations.bibliography([cite_ref()], style)[0]["text"]
