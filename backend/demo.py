"""Clearly labelled sample data so the screens are not empty on first launch.

Everything created here has demo = 1: it can never be verified, accepted for citation or
counted in the overview metrics.
"""
from . import concepts, db
from .evidence import claim_status

DEMO_QUESTION = ("Does AI-powered personalisation improve customer experience in ecommerce, "
                 "and what risks or limitations have researchers identified?")


def seed_demo(con) -> None:
    pid = db.new_id()
    plan = concepts.template_plan(DEMO_QUESTION)
    db.insert(con, "projects", {"id": pid, "title": "Sample project — AI personalisation (demo data)",
                                "question": DEMO_QUESTION, "plan": plan, "plan_approved_at": db.now(), "demo": 1,
                                "created_at": db.now()})
    sources = [
        ("Illustrative study A: personalisation and satisfaction (synthetic)", "Demo Author A",
         "In this synthetic example, shoppers who received relevant recommendations reported higher satisfaction. "
         "The design was cross-sectional, so it does not establish causation."),
        ("Illustrative study B: personalisation and privacy concern (synthetic)", "Demo Author B",
         "In this synthetic example, participants reported lower trust when recommendations revealed unexpected tracking. "
         "Effects were smaller for users who understood how their data was used."),
    ]
    ref_ids = []
    for title, author, abstract in sources:
        rid = db.new_id()
        ref_ids.append(rid)
        db.insert(con, "refs", {"id": rid, "project_id": pid, "title": title, "authors": [{"given": "", "family": author}],
                                "year": "2025", "journal": "Synthetic example — not a real journal", "abstract": abstract,
                                "metadata_source": "Demo data", "demo": 1, "folder": "Demo",
                                "notes": "Illustrative only. Not a published paper.", "created_at": db.now(), "updated_at": db.now()})
    claims = [
        ("Relevant recommendations may improve customer satisfaction.", 0,
         "shoppers who received relevant recommendations reported higher satisfaction", "supports"),
        ("Intrusive personalisation may reduce customer trust.", 1,
         "participants reported lower trust when recommendations revealed unexpected tracking", "supports"),
        ("AI personalisation always increases customer retention.", None, None, None),
    ]
    for text, ref_index, passage, stance in claims:
        cid = db.new_id()
        db.insert(con, "claims", {"id": cid, "project_id": pid, "text": text, "demo": 1, "created_at": db.now(), "updated_at": db.now()})
        if ref_index is not None:
            db.insert(con, "evidence_records", {"id": db.new_id(), "claim_id": cid, "reference_id": ref_ids[ref_index],
                                                "passage": passage, "location": "abstract", "match": "exact",
                                                "stance": stance, "created_at": db.now()})
        c = db.get(con, "claims", cid)
        status, reason, level = claim_status(c, [], {})
        db.update(con, "claims", cid, {"status": status, "status_reason": reason, "evidence_level": level})
    db.audit(con, "Sample project loaded", actor="System", project_id=pid, details="Synthetic, clearly labelled demo data")
