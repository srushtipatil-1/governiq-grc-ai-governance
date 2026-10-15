"""Phase 6b tests: automated checks read system exports and feed the normal test and finding workflow."""

import pytest
from sqlalchemy import select

from governiq.automation import CHECKS, CHECKS_BY_CODE, EXPORTS_TAKEN_ON, SYSTEMS_DIR, run_check
from governiq.models import ControlTest, Finding


@pytest.mark.parametrize(
    ("code", "population", "exceptions"),
    [("CCM-01", 5, 1), ("CCM-02", 4, 1), ("CCM-03", 8, 0), ("CCM-04", 4, 0), ("CCM-05", 4, 0)],
)
def test_each_check_finds_the_planted_exceptions(code, population, exceptions):
    result = CHECKS_BY_CODE[code].run(SYSTEMS_DIR, EXPORTS_TAKEN_ON)
    assert (result.population, len(result.exceptions)) == (population, exceptions)


def test_leaver_check_names_the_leaver():
    result = CHECKS_BY_CODE["CCM-01"].run(SYSTEMS_DIR, EXPORTS_TAKEN_ON)
    assert result.exceptions[0]["username"] == "imran.q"


def test_every_check_points_at_a_real_control(session):
    from governiq.models import Control

    codes = set(session.scalars(select(Control.code)))
    assert {c.control_code for c in CHECKS} <= codes


def test_failed_check_records_an_automated_test_and_opens_a_finding(session):
    result, outcome = run_check(session, "CCM-02", actor="priya.analyst")
    assert outcome.test.method == "Automated"
    assert outcome.test.sample_size == result.population
    assert outcome.test.result == "Ineffective"
    assert outcome.opened.code == "FND-005"
    assert len(outcome.test.evidence) == 1


def test_passing_patch_check_closes_the_patch_finding(session):
    _, outcome = run_check(session, "CCM-04", actor="priya.analyst")
    assert outcome.test.result == "Effective"
    assert [f.code for f in outcome.closed] == ["FND-002"]


def test_rerunning_a_failing_check_does_not_duplicate_findings(session):
    run_check(session, "CCM-01", actor="priya.analyst")
    run_check(session, "CCM-01", actor="priya.analyst")
    control_findings = session.scalars(select(Finding).where(Finding.status == "Open")).all()
    titles = [f.control.code for f in control_findings]
    assert titles.count("CTL-IAM-02") == 1


def test_only_testers_can_run_checks(session):
    before = len(session.scalars(select(ControlTest)).all())
    with pytest.raises(ValueError, match="GRC Analyst"):
        run_check(session, "CCM-03", actor="arjun.audit")
    assert len(session.scalars(select(ControlTest)).all()) == before
