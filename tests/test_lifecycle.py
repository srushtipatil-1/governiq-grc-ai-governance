"""Phase 8 tests: model cards, stage gates with the go-live checklist, and post-implementation reviews."""

from datetime import date

import pytest
from sqlalchemy import select

from governiq.ai_governance import (
    QUESTIONS,
    NewAISystem,
    decide_assessment,
    register_ai_system,
    submit_assessment,
)
from governiq.lifecycle import (
    MODEL_CARD_FIELDS,
    advance_stage,
    card_for,
    gate_checklist,
    missing_card_fields,
    model_card_markdown,
    next_review_due,
    record_review,
    retire_system,
    review_status,
    reviews_for,
    save_model_card,
)
from governiq.models import AISystem, StageGate, User

FULL_CARD = {
    field: f"{label} written out in enough detail to be useful." for field, label, _ in MODEL_CARD_FIELDS
}
ALL_YES = {q.id: "Yes" for q in QUESTIONS}


def _system(session, code):
    return session.scalar(select(AISystem).where(AISystem.code == code))


def _new_system(session) -> str:
    """CollectWise: a new tier-2 system with no risks, so it can pass every gate with the paperwork done."""
    system = register_ai_system(
        session,
        NewAISystem(
            name="CollectWise",
            purpose="Predicts which borrowers will miss an EMI",
            domain="Other",
            model_type="Logistic regression",
            build_type="Built in-house",
            owner_username="vikram.eng",
            vendor_code=None,
            uses_personal_data=True,
            people_affected=50_000,
            decides_on_individuals=False,
            interacts_with_people=False,
            autonomy="Human in the loop",
        ),
        actor="priya.analyst",
    )
    return system.code


def _approve(session, code):
    assessment = submit_assessment(session, code, ALL_YES, actor="priya.analyst").assessment
    decide_assessment(session, assessment.code, True, "", actor="meera.aigov")


# ---------------------------------------------------------------- model cards
def test_seeded_cards_show_what_is_missing(session):
    assert missing_card_fields(_system(session, "AI-01"), card_for(session, _system(session, "AI-01"))) == []
    sahayak = _system(session, "AI-03")
    assert missing_card_fields(sahayak, card_for(session, sahayak)) == ["Performance", "Fairness"]
    assert len(missing_card_fields(_system(session, "AI-04"), None)) == 7  # no transparency notice needed


def test_transparency_notice_required_only_for_systems_that_talk_to_people(session):
    sahayak = _system(session, "AI-03")
    card = card_for(session, sahayak)
    card.transparency_notice = ""
    assert "Transparency notice" in missing_card_fields(sahayak, card)


def test_saving_a_card_bumps_the_version(session):
    card = save_model_card(
        session, "AI-03", {"performance": "Answer accuracy 94% on 200 FAQ questions."}, "vikram.eng"
    )
    assert card.version == 2
    with pytest.raises(ValueError, match="Nothing changed"):
        save_model_card(
            session, "AI-03", {"performance": "Answer accuracy 94% on 200 FAQ questions."}, "vikram.eng"
        )


def test_only_owner_or_governance_can_edit_a_card(session):
    with pytest.raises(ValueError, match="the owner"):
        save_model_card(session, "AI-03", FULL_CARD, "neha.hr")


def test_card_exports_as_markdown(session):
    system = _system(session, "AI-01")
    text = model_card_markdown(system, card_for(session, system))
    assert text.startswith("# Model card: CreditLens (AI-01)")
    assert "## Human oversight" in text and "Transparency notice" not in text


# ---------------------------------------------------------------- gates
def test_sahayak_go_live_is_blocked_with_reasons(session):
    failed = {
        item.label: item.detail for item in gate_checklist(session, _system(session, "AI-03")) if not item.ok
    }
    assert failed == {
        "Risk assessment approved": "No assessment yet",
        "Model card complete": "Missing: Performance, Fairness",
        "No open findings on its controls": "FND-004 on CTL-AI-09",
    }
    with pytest.raises(ValueError, match="cannot move to Deployed"):
        advance_stage(session, "AI-03", "meera.aigov")
    assert _system(session, "AI-03").lifecycle_stage == "Validate"


def test_new_system_passes_every_gate_once_paperwork_is_done(session):
    code = _new_system(session)
    with pytest.raises(ValueError, match="Risk assessment approved"):
        advance_stage(session, code, "priya.analyst")
    _approve(session, code)
    advance_stage(session, code, "priya.analyst")  # Design -> Build
    with pytest.raises(ValueError, match="Model card complete"):
        advance_stage(session, code, "priya.analyst")
    save_model_card(session, code, FULL_CARD, "vikram.eng")
    advance_stage(session, code, "priya.analyst")  # Build -> Validate
    with pytest.raises(ValueError, match="Only the AI Governance Lead"):
        advance_stage(session, code, "priya.analyst")
    gate = advance_stage(session, code, "meera.aigov", "Approved for pilot", today=date(2026, 10, 15))
    system = _system(session, code)
    assert (system.lifecycle_stage, system.deployed_on) == ("Deployed", date(2026, 10, 15))
    assert gate.from_stage == "Validate" and "Model card complete" in gate.checklist_json
    assert session.query(StageGate).count() == 3


def test_owner_cannot_approve_own_go_live(session):
    code = _new_system(session)
    system = _system(session, code)
    system.lifecycle_stage = "Validate"
    system.owner = session.scalar(select(User).where(User.username == "meera.aigov"))
    session.commit()
    with pytest.raises(ValueError, match="cannot approve their own go-live"):
        advance_stage(session, code, "meera.aigov")


def test_retiring_needs_the_lead_and_a_reason(session):
    with pytest.raises(ValueError, match="Only the AI Governance Lead"):
        retire_system(session, "AI-02", "priya.analyst", "Replaced by a new vendor")
    with pytest.raises(ValueError, match="at least 10"):
        retire_system(session, "AI-02", "meera.aigov", "old")
    retire_system(session, "AI-02", "meera.aigov", "Replaced by a new vendor")
    assert _system(session, "AI-02").lifecycle_stage == "Retired"
    assert gate_checklist(session, _system(session, "AI-02")) == []


# ---------------------------------------------------------------- reviews
def test_review_schedule_follows_internal_tier(session):
    creditlens, fraudshield = _system(session, "AI-01"), _system(session, "AI-02")
    assert next_review_due(creditlens, reviews_for(session, creditlens)) == date(
        2026, 11, 1
    )  # 180 days after PIR
    assert next_review_due(fraudshield, []) == date(2026, 6, 15)  # tier 2: a year after go-live
    assert review_status(date(2026, 6, 15), today=date(2026, 10, 15)) == "Overdue"
    assert review_status(date(2026, 11, 1), today=date(2026, 10, 15)) == "Due soon"
    assert review_status(date(2027, 3, 1), today=date(2026, 10, 15)) == "On track"
    assert next_review_due(_system(session, "AI-03"), []) is None


def test_recording_a_review_resets_the_clock(session):
    review = record_review(
        session, "AI-02", "Continue", "Precision 90% on July sample; no region skew.", "priya.analyst",
        today=date(2026, 10, 15),
    )  # fmt: skip
    assert review.code == "PIR-002"
    assert next_review_due(
        _system(session, "AI-02"), reviews_for(session, _system(session, "AI-02"))
    ) == date(2027, 10, 15)


@pytest.mark.parametrize(
    ("system", "actor", "outcome", "notes", "message"),
    [("AI-03", "priya.analyst", "Continue", "x" * 30, "not live"),
     ("AI-02", "rahul.itops", "Continue", "x" * 30, "Only a GRC Analyst"),
     ("AI-02", "priya.analyst", "Maybe", "x" * 30, "Outcome must be"),
     ("AI-02", "priya.analyst", "Continue", "fine", "at least 20")],
    ids=["not-live", "wrong-role", "bad-outcome", "thin-notes"],
)  # fmt: skip
def test_review_rules(session, system, actor, outcome, notes, message):
    with pytest.raises(ValueError, match=message):
        record_review(session, system, outcome, notes, actor)
