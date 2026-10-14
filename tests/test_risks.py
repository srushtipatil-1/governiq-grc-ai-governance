"""Phase 4 tests: the risk methodology is implemented exactly as documented."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from governiq.models import AuditLog, Risk
from governiq.risks import (
    NewRisk,
    create_risk,
    heatmap_counts,
    load_risks,
    next_risk_code,
    rating_for,
    rating_summary,
    residual_errors,
    score,
    validate_new_risk,
)


@pytest.mark.parametrize(
    ("value", "rating"),
    [
        (1, "Low"),
        (4, "Low"),
        (5, "Medium"),
        (9, "Medium"),
        (10, "High"),
        (16, "High"),
        (20, "Critical"),
        (25, "Critical"),
    ],
)
def test_rating_bands_match_the_methodology(value, rating):
    assert rating_for(value) == rating


def test_score_is_likelihood_times_impact():
    assert score(4, 4) == 16


@pytest.mark.parametrize(("likelihood", "impact"), [(0, 3), (6, 3), (3, 0), (3, 6)])
def test_score_rejects_values_outside_1_to_5(likelihood, impact):
    with pytest.raises(ValueError):
        score(likelihood, impact)


def test_residual_cannot_exceed_inherent():
    errors = residual_errors(
        inherent=12, residual_likelihood=4, residual_impact=4, has_effective_control=True
    )
    assert any("cannot be higher" in e for e in errors)


def test_residual_reduction_needs_a_tested_effective_control():
    errors = residual_errors(
        inherent=16, residual_likelihood=2, residual_impact=4, has_effective_control=False
    )
    assert any("passed its latest operating effectiveness test" in e for e in errors)


def test_residual_reduction_allowed_with_effective_control():
    assert residual_errors(16, 2, 4, has_effective_control=True) == []


def _new_risk(**changes) -> NewRisk:
    values = {
        "title": "Loan officers export customer lists to USB drives",
        "category": "Privacy",
        "owner_username": "sana.dpo",
        "likelihood": 3,
        "impact": 4,
        "treatment": "Mitigate",
        "due_date": date.today() + timedelta(days=30),
        "control_codes": ["CTL-OPS-05"],
    }
    values.update(changes)
    return NewRisk(**values)


def test_valid_new_risk_has_no_errors():
    assert validate_new_risk(_new_risk()) == []


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"title": "Too short"}, "Title"),
        ({"category": "Weather"}, "Category"),
        ({"due_date": date(2020, 1, 1)}, "future"),
        ({"control_codes": []}, "at least one control"),
        ({"likelihood": 7}, "Likelihood"),
    ],
)
def test_invalid_new_risk_is_explained(changes, message):
    errors = validate_new_risk(_new_risk(**changes))
    assert any(message in e for e in errors)


def test_accepted_risk_may_have_no_control():
    assert validate_new_risk(_new_risk(treatment="Accept", control_codes=[])) == []


def test_next_code_follows_the_highest_existing_code(session):
    assert next_risk_code(session) == "RSK-031"


def test_create_risk_saves_and_writes_an_audit_entry(session):
    saved = create_risk(session, _new_risk(), actor="priya.analyst")
    assert saved.code == "RSK-031"
    assert saved.inherent_score == 12
    entry = session.scalar(select(AuditLog).where(AuditLog.entity_id == "RSK-031"))
    assert entry.action == "create"
    assert entry.username == "priya.analyst"
    assert '"CTL-OPS-05"' in entry.after_json


def test_create_risk_rejects_unknown_owner_and_control(session):
    with pytest.raises(ValueError, match="does not exist") as problem:
        create_risk(session, _new_risk(owner_username="ghost.user", control_codes=["CTL-NOPE"]), actor="x")
    assert "CTL-NOPE" in str(problem.value)
    assert session.scalar(select(Risk).where(Risk.code == "RSK-031")) is None


def test_heatmap_accounts_for_every_risk(session):
    risks = load_risks(session)
    counts = heatmap_counts(risks)
    assert len(counts) == 25
    assert sum(counts.values()) == len(risks) == 30
    assert counts[(4, 4)] == 2  # RSK-004 and RSK-023


def test_rating_summary_adds_up(session):
    summary = rating_summary(load_risks(session))
    assert sum(summary.values()) == 30
    assert summary["Critical"] == 1  # RSK-001 ransomware, 4 x 5
