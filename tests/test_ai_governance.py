"""Phase 7 tests: purpose-based tiering, AI inventory intake and the independent assessment workflow."""

from datetime import date

import pytest
from sqlalchemy import select

from governiq.ai_governance import (
    QUESTIONS,
    NewAISystem,
    classify,
    decide_assessment,
    function_scores,
    register_ai_system,
    submit_assessment,
)
from governiq.models import AISystem, AuditLog, Risk

ALL_YES = {q.id: "Yes" for q in QUESTIONS}


def _system(**changes) -> NewAISystem:
    values = dict(
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
    )
    values.update(changes)
    return NewAISystem(**values)


@pytest.mark.parametrize(
    ("name", "external", "internal"),
    [("CreditLens", "High risk", 1), ("TalentSift", "High risk", 1), ("Sahayak", "Limited risk", 1),
     ("FraudShield", "Minimal risk", 2)],
)  # fmt: skip
def test_seeded_systems_are_classified(session, name, external, internal):
    system = session.scalar(select(AISystem).where(AISystem.name == name))
    assert (system.external_tier, system.internal_tier) == (external, internal)
    assert system.tier_reasons


def test_fraud_detection_is_not_high_risk_but_still_gets_internal_attention():
    external, internal, reasons = classify(
        "Fraud detection", False, True, 1_200_000, False, "Human in the loop"
    )
    assert (external, internal) == ("Minimal risk", 2)
    assert any("carved out" in r for r in reasons)


def test_low_impact_internal_tool_is_tier_3():
    assert classify("Internal productivity", False, False, 200, False, "Human in the loop")[:2] == (
        "Minimal risk",
        3,
    )


def test_registering_a_system_classifies_and_logs_it(session):
    system = register_ai_system(session, _system(domain="Credit decisions"), actor="priya.analyst")
    assert (system.code, system.external_tier, system.internal_tier) == ("AI-05", "High risk", 1)
    log = session.scalar(select(AuditLog).where(AuditLog.entity_id == "AI-05"))
    assert log.action == "register"


def test_prohibited_use_is_refused(session):
    with pytest.raises(ValueError, match="cannot be built or bought"):
        register_ai_system(session, _system(domain="Social scoring"), actor="priya.analyst")
    assert session.scalar(select(AISystem).where(AISystem.name == "CollectWise")) is None


@pytest.mark.parametrize(
    ("changes", "actor", "message"),
    [({}, "rahul.itops", "Only a GRC Analyst"), ({"name": "Sahayak"}, "priya.analyst", "already registered"),
     ({"build_type": "Bought"}, "priya.analyst", "needs its vendor"),
     ({"owner_username": "arjun.audit"}, "priya.analyst", "business owner")],
    ids=["wrong-role", "duplicate", "no-vendor", "auditor-owner"],
)  # fmt: skip
def test_register_rules(session, changes, actor, message):
    with pytest.raises(ValueError, match=message):
        register_ai_system(session, _system(**changes), actor=actor)


def test_function_scores_ignore_not_applicable():
    answers = {**ALL_YES, "ME4": "Not applicable", "ME1": "No", "ME2": "Partial"}
    assert function_scores(answers)["Measure"] == 50  # (0 + 0.5 + 1) / 3
    assert function_scores(answers)["Govern"] == 100


def test_gaps_on_important_questions_become_ai_risks(session):
    answers = {**ALL_YES, "ME2": "No", "M4": "Partial", "MA1": "No", "G4": "Not applicable"}
    outcome = submit_assessment(session, "AI-04", answers, actor="priya.analyst", today=date(2026, 10, 15))
    assert outcome.assessment.status == "Submitted"
    titles = sorted(r.title for r in outcome.risks_created)
    assert titles == [
        "TalentSift: fairness across groups not tested",
        "TalentSift: no defined human oversight",
    ]
    fairness = next(r for r in outcome.risks_created if "fairness" in r.title)
    assert (fairness.likelihood, fairness.impact, fairness.category) == (4, 5, "AI")
    assert fairness.ai_system.name == "TalentSift"
    assert [c.code for c in fairness.controls] == ["CTL-AI-05"]
    assert fairness.source == "AI assessment AIA-002"


def test_reassessment_does_not_duplicate_risks(session):
    answers = {**ALL_YES, "ME2": "No"}
    first = submit_assessment(session, "AI-04", answers, actor="priya.analyst")
    decide_assessment(session, first.assessment.code, False, "Fairness test missing", actor="meera.aigov")
    second = submit_assessment(session, "AI-04", answers, actor="priya.analyst")
    assert second.risks_created == []
    assert session.query(Risk).count() == 31


@pytest.mark.parametrize(
    ("system", "answers", "actor", "message"),
    [("AI-04", ALL_YES, "rahul.itops", "Only a GRC Analyst"),
     ("AI-01", ALL_YES, "priya.analyst", None),
     ("AI-04", {"G1": "Yes"}, "priya.analyst", "Answer every question"),
     ("AI-04", {**ALL_YES, "G1": "Not applicable"}, "priya.analyst", "not allowed")],
    ids=["wrong-role", "ok-reassess-creditlens", "incomplete", "na-not-allowed"],
)  # fmt: skip
def test_submit_rules(session, system, answers, actor, message):
    if message is None:
        assert submit_assessment(session, system, answers, actor=actor).assessment.code == "AIA-002"
    else:
        with pytest.raises(ValueError, match=message):
            submit_assessment(session, system, answers, actor=actor)


def test_owner_cannot_assess_own_system(session):
    register_ai_system(session, _system(owner_username="meera.aigov"), actor="priya.analyst")
    with pytest.raises(ValueError, match="owns CollectWise"):
        submit_assessment(session, "AI-05", ALL_YES, actor="meera.aigov")


def test_second_submission_waits_for_decision(session):
    submit_assessment(session, "AI-04", ALL_YES, actor="priya.analyst")
    with pytest.raises(ValueError, match="still waiting"):
        submit_assessment(session, "AI-04", ALL_YES, actor="meera.aigov")


@pytest.mark.parametrize(
    ("actor", "approve", "note", "message"),
    [("priya.analyst", True, "", "Only the AI Governance Lead"), ("meera.aigov", False, "no", "at least 10")],
    ids=["analyst-cannot-approve", "rejection-needs-reason"],
)
def test_decision_rules(session, actor, approve, note, message):
    code = submit_assessment(session, "AI-04", ALL_YES, actor="priya.analyst").assessment.code
    with pytest.raises(ValueError, match=message):
        decide_assessment(session, code, approve, note, actor=actor)


def test_lead_cannot_approve_own_assessment(session):
    code = submit_assessment(session, "AI-04", ALL_YES, actor="meera.aigov").assessment.code
    with pytest.raises(ValueError, match="different person"):
        decide_assessment(session, code, True, "", actor="meera.aigov")


def test_approval_is_recorded_once(session):
    code = submit_assessment(session, "AI-04", ALL_YES, actor="priya.analyst").assessment.code
    approved = decide_assessment(session, code, True, "Looks complete", actor="meera.aigov")
    assert (approved.status, approved.approver.username) == ("Approved", "meera.aigov")
    with pytest.raises(ValueError, match="already been approved"):
        decide_assessment(session, code, False, "Changed my mind", actor="meera.aigov")
