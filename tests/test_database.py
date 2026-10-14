"""Phase 3 tests: the seed data loads, links correctly and the database rejects bad values."""

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from governiq.db import create_tables, make_engine, make_session_factory
from governiq.models import AISystem, Control, Framework, Requirement, Risk, User
from governiq.seed import seed


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_seed_counts(session):
    assert count(session, User) == 9
    assert count(session, AISystem) == 4
    assert count(session, Framework) == 7
    assert count(session, Requirement) == 85
    assert count(session, Control) == 33
    assert count(session, Risk) == 30


def test_every_risk_has_an_owner_and_at_least_one_control(session):
    for risk in session.scalars(select(Risk)):
        assert risk.owner is not None
        assert len(risk.controls) >= 1, f"{risk.code} has no control"


def test_every_control_maps_to_a_framework_requirement(session):
    for control in session.scalars(select(Control)):
        assert len(control.requirements) >= 1, f"{control.code} maps to nothing"


def test_one_control_can_satisfy_several_frameworks(session):
    review = session.scalar(select(Control).where(Control.code == "CTL-IAM-03"))
    frameworks = {req.framework.code for req in review.requirements}
    assert frameworks == {"ISO27001", "NISTCSF", "DPDP"}


def test_ai_risks_link_to_ai_systems(session):
    risk = session.scalar(select(Risk).where(Risk.code == "RSK-020"))
    assert risk.ai_system.name == "CreditLens"
    assert risk.inherent_score == 15


def test_database_rejects_likelihood_outside_1_to_5(session):
    owner = session.scalar(select(User).where(User.username == "priya.analyst"))
    session.add(
        Risk(
            code="RSK-999",
            title="Bad score",
            category="Cyber",
            owner=owner,
            likelihood=6,
            impact=3,
            treatment="Mitigate",
            due_date=date(2027, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_unknown_role(session):
    session.add(User(username="x.y", full_name="X", role="Superuser", department="IT"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_seed_reports_unknown_reference_clearly(tmp_path):
    import shutil

    from governiq.seed import SEED_DIR

    bad_dir = tmp_path / "seed"
    shutil.copytree(SEED_DIR, bad_dir)
    risks = (bad_dir / "risks.csv").read_text(encoding="utf-8").replace("CTL-OPS-01;", "CTL-NOPE-99;", 1)
    (bad_dir / "risks.csv").write_text(risks, encoding="utf-8")

    engine = make_engine(f"sqlite:///{tmp_path / 'bad.db'}")
    create_tables(engine)
    with make_session_factory(engine)() as db, pytest.raises(ValueError, match="CTL-NOPE-99"):
        seed(db, bad_dir)
