"""Phase 9 tests: validation metrics, fairness, drift and recording a validation as control tests."""

import pytest
from sqlalchemy import select

from governiq.model_risk import auc, confusion, evaluate, psi, psi_band, rates, record_validation
from governiq.models import Finding, ModelValidation


# ---------------------------------------------------------------- metric maths on hand-checkable data
def test_auc_hand_examples():
    assert auc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == 1.0  # perfect separation
    assert auc([0.1, 0.2, 0.8, 0.9], [1, 1, 0, 0]) == 0.0  # perfectly wrong
    assert auc([0.5, 0.5], [1, 0]) == 0.5  # a tie counts half
    assert auc([0.9, 0.4, 0.6, 0.1], [1, 1, 0, 0]) == 0.75  # 3 of 4 good-bad pairs ordered correctly


def test_auc_needs_both_outcomes():
    with pytest.raises(ValueError, match="both"):
        auc([0.3, 0.7], [1, 1])


def test_confusion_and_rates():
    scores, labels = [0.9, 0.7, 0.65, 0.3, 0.1], [1, 0, 1, 1, 0]
    assert confusion(scores, labels, 0.62) == {"tp": 2, "fp": 1, "tn": 1, "fn": 1}
    r = rates(scores, labels, 0.62)
    assert r["approval_rate"] == pytest.approx(0.6)
    assert r["precision"] == pytest.approx(2 / 3)
    assert r["tpr"] == pytest.approx(2 / 3)


def test_psi_is_zero_for_identical_distributions_and_grows_with_shift():
    base = [i / 100 for i in range(100)]
    assert psi(base, base)[0] == pytest.approx(0.0)
    shifted = [max(0.0, v - 0.2) for v in base]
    assert psi(base, shifted)[0] > 0.25
    assert len(psi(base, base)[1]) == 10


@pytest.mark.parametrize(
    ("value", "band"), [(0.05, "Stable"), (0.12, "Moderate shift, watch"), (0.3, "Significant shift")]
)
def test_psi_bands(value, band):
    assert psi_band(value) == band


# ---------------------------------------------------------------- CreditLens synthetic validation
def test_creditlens_results_match_the_model_card():
    e = evaluate("AI-01")
    values = {c.name: (round(c.value, 3), c.ok) for c in e.checks}
    assert e.sample == 2000
    assert values["AUC"] == (0.797, True)
    assert values["Approval rate ratio by gender"] == (
        0.854,
        False,
    )  # fails 0.90 appetite, passes four-fifths
    assert values["Approval rate ratio by region"] == (0.921, True)
    assert values["PSI, September 2026 vs validation"] == (0.123, True)
    assert not e.passed


def test_unconfigured_model_is_refused():
    with pytest.raises(ValueError, match="No validation data"):
        evaluate("AI-04")


def test_recording_a_validation_creates_three_tests_and_keeps_fairness_finding_open(session):
    run = record_validation(session, "AI-01", "priya.analyst")
    assert (run.code, run.result) == ("MV-001", "Fail")
    assert len(run.test_codes.split(", ")) == 3
    open_on_fairness = session.scalars(
        select(Finding).where(Finding.status == "Open").join(Finding.control)
    ).all()
    assert [f.code for f in open_on_fairness if f.control.code == "CTL-AI-05"] == ["FND-003"]  # no duplicate
    assert not [f for f in open_on_fairness if f.control.code in ("CTL-AI-04", "CTL-AI-06")]


@pytest.mark.parametrize(
    ("actor", "message"),
    [("vikram.eng", "Only a GRC Analyst"), ("meera.aigov", "owns CTL-AI-04"), ("arjun.audit", "Only a GRC")],
    ids=["model-owner", "owns-validation-control", "auditor"],
)
def test_validation_must_be_independent(session, actor, message):
    with pytest.raises(ValueError, match=message):
        record_validation(session, "AI-01", actor)
    assert session.query(ModelValidation).count() == 0
