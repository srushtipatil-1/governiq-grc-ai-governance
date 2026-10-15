"""Phase 6 tests: testing rules, segregation of duties, evidence integrity, findings and residual risk."""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from governiq.assurance import (
    MAX_EVIDENCE_BYTES,
    NewTest,
    add_action,
    complete_action,
    effective_controls,
    evidence_dir,
    load_findings,
    record_test,
    rerate_residual,
    verify_evidence,
)
from governiq.models import AuditLog, ControlTest, Evidence, Finding, Risk, User

EVIDENCE = [("sample.csv", b"user,status\nanita,disabled\n")]


def _test(**changes) -> NewTest:
    values = {
        "control_code": "CTL-OPS-02",
        "test_type": "Operating",
        "method": "Inspection",
        "period": "2026-Q4",
        "sample_size": 2,
        "exceptions": 0,
        "performed_on": date.today(),
        "reviewer_username": "kabir.ciso",
    }
    values.update(changes)
    return NewTest(**values)


def _finding(session, code) -> Finding:
    return session.scalar(select(Finding).where(Finding.code == code))


# ---------------- seeded state
def test_seed_creates_tests_findings_and_effective_controls(session):
    assert session.scalar(select(func.count()).select_from(ControlTest)) == 11
    assert [f.code for f in load_findings(session)] == ["FND-001", "FND-002", "FND-003", "FND-004"]
    assert effective_controls(session) == {
        "CTL-IAM-03",
        "CTL-IAM-04",
        "CTL-OPS-01",
        "CTL-OPS-05",
        "CTL-PRV-01",
        "CTL-TPR-01",
    }


# ---------------- result and findings
def test_result_comes_from_exceptions_not_from_the_user(session):
    outcome = record_test(session, _test(exceptions=1), "priya.analyst", EVIDENCE)
    assert outcome.test.result == "Ineffective"


def test_failed_key_control_opens_a_high_finding(session):
    outcome = record_test(
        session, _test(control_code="CTL-IAM-04", exceptions=1, sample_size=1), "priya.analyst", EVIDENCE
    )
    assert outcome.opened.code == "FND-005"
    assert outcome.opened.severity == "High"


def test_second_failure_does_not_duplicate_an_open_finding(session):
    outcome = record_test(
        session, _test(control_code="CTL-IAM-02", sample_size=25, exceptions=3), "priya.analyst", EVIDENCE
    )
    assert outcome.opened is None
    assert session.scalar(select(func.count()).select_from(Finding)) == 4


def test_passing_retest_closes_finding_when_all_actions_are_done(session):
    outcome = record_test(session, _test(), "priya.analyst", EVIDENCE)  # CTL-OPS-02, ACT-002 already done
    assert [f.code for f in outcome.closed] == ["FND-002"]
    assert _finding(session, "FND-002").status == "Closed"
    assert _finding(session, "FND-002").closed_by_test_id == outcome.test.id


def test_passing_retest_leaves_finding_open_while_actions_are_open(session):
    outcome = record_test(
        session, _test(control_code="CTL-IAM-02", sample_size=25), "priya.analyst", EVIDENCE
    )
    assert [f.code for f in outcome.still_open] == ["FND-001"]
    assert _finding(session, "FND-001").status == "Open"


def test_design_test_cannot_close_a_finding(session):
    outcome = record_test(session, _test(test_type="Design", sample_size=1), "priya.analyst", EVIDENCE)
    assert outcome.closed == []
    assert _finding(session, "FND-002").status == "Open"


# ---------------- segregation of duties and validation
@pytest.mark.parametrize(
    ("changes", "actor", "message"),
    [
        ({"control_code": "CTL-TPR-01"}, "priya.analyst", "owns CTL-TPR-01"),
        ({}, "rahul.itops", "Only a GRC Analyst"),
        ({}, "arjun.audit", "Only a GRC Analyst"),
        ({"reviewer_username": "priya.analyst"}, "priya.analyst", "different person from the tester"),
        ({"reviewer_username": "rahul.itops"}, "priya.analyst", "control owner cannot review"),
        ({"reviewer_username": "arjun.audit"}, "priya.analyst", "Admins and auditors cannot review"),
        ({"test_type": "Design", "sample_size": 5}, "priya.analyst", "walkthrough of one item"),
        ({"exceptions": 3}, "priya.analyst", "between 0 and the sample size"),
        ({"performed_on": date.today() + timedelta(days=1)}, "priya.analyst", "cannot be in the future"),
        ({"period": "  "}, "priya.analyst", "period tested"),
    ],
)
def test_invalid_tests_are_rejected_with_a_reason(session, changes, actor, message):
    with pytest.raises(ValueError, match=message):
        record_test(session, _test(**changes), actor, EVIDENCE)
    assert session.scalar(select(func.count()).select_from(ControlTest)) == 11


def test_a_test_needs_evidence(session):
    with pytest.raises(ValueError, match="Attach at least one evidence file"):
        record_test(session, _test(), "priya.analyst", [])


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("payload.exe", b"MZ", "not allowed"),
        ("empty.csv", b"", "empty"),
        ("huge.csv", b"x" * (MAX_EVIDENCE_BYTES + 1), "larger than 10 MB"),
    ],
    # Short names: by default pytest would put the 10 MB value itself into the test ID,
    # which is longer than Windows allows for an environment variable.
    ids=["blocked-file-type", "empty-file", "too-large"],
)
def test_unsafe_evidence_files_are_rejected(session, filename, content, message):
    with pytest.raises(ValueError, match=message):
        record_test(session, _test(), "priya.analyst", [(filename, content)])


def test_database_also_blocks_tester_reviewing_own_test(session):
    """Defence in depth: even code that skips the rules cannot save tester == reviewer."""
    test = session.scalar(select(ControlTest).where(ControlTest.code == "TST-001"))
    test.reviewer_id = test.tester_id
    with pytest.raises(IntegrityError):
        session.commit()


# ---------------- evidence integrity
def test_evidence_is_stored_under_a_random_name_and_verifies(session):
    outcome = record_test(session, _test(), "priya.analyst", EVIDENCE)
    evidence = outcome.test.evidence[0]
    assert evidence.filename == "sample.csv"
    assert evidence.stored_name != "sample.csv" and evidence.stored_name.endswith(".csv")
    assert verify_evidence(evidence)


def test_tampered_evidence_fails_verification(session):
    evidence = session.scalar(select(Evidence).where(Evidence.code == "EV-0002"))
    assert verify_evidence(evidence)
    (evidence_dir() / evidence.stored_name).write_bytes(b"edited after upload")
    assert not verify_evidence(evidence)


# ---------------- actions
def test_action_owner_can_complete_their_action(session):
    assert complete_action(session, "ACT-001", "rahul.itops").status == "Done"


def test_unrelated_user_cannot_complete_an_action(session):
    with pytest.raises(ValueError, match="Only the action owner"):
        complete_action(session, "ACT-001", "neha.hr")


def test_add_action_rules(session):
    future = date.today() + timedelta(days=20)
    with pytest.raises(ValueError, match="Only a GRC Analyst"):
        add_action(session, "FND-001", "Automate account disable", "rahul.itops", future, "rahul.itops")
    with pytest.raises(ValueError, match="due date must be in the future"):
        add_action(
            session, "FND-001", "Automate account disable", "rahul.itops", date.today(), "priya.analyst"
        )
    action = add_action(
        session, "FND-001", "Automate account disable", "rahul.itops", future, "priya.analyst"
    )
    assert action.code == "ACT-005"


# ---------------- residual risk
def test_residual_can_drop_when_a_linked_control_is_proven_effective(session):
    risk = rerate_residual(session, "RSK-004", 2, 4, "priya.analyst")  # CTL-IAM-03 passed
    assert (risk.residual_likelihood, risk.residual_impact) == (2, 4)


def test_residual_cannot_drop_without_an_effective_control(session):
    with pytest.raises(ValueError, match="passed its latest operating effectiveness test"):
        rerate_residual(session, "RSK-020", 1, 5, "priya.analyst")  # CreditLens fairness control failed


def test_only_analysts_rerate_residual(session):
    with pytest.raises(ValueError, match="Only a GRC Analyst"):
        rerate_residual(session, "RSK-001", 2, 5, "rahul.itops")


def test_seeded_residual_ratings_respect_the_rules(session):
    rated = session.scalars(select(Risk).where(Risk.residual_likelihood.is_not(None))).all()
    assert {r.code for r in rated} == {"RSK-001", "RSK-011", "RSK-015", "RSK-017"}


def test_every_change_is_audit_logged(session):
    record_test(session, _test(), "priya.analyst", EVIDENCE)
    entries = session.scalars(select(AuditLog).where(AuditLog.username == "priya.analyst")).all()
    assert {"create", "open", "close", "rerate"} <= {e.action for e in entries}
    assert session.scalar(select(User).where(User.username == "priya.analyst")) is not None
