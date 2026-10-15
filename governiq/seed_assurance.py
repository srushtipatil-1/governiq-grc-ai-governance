"""Seed the Q3 2026 control tests, their evidence, findings and corrective actions (all synthetic).

Tests go through record_test(), the same function the app uses, so seeded data obeys every rule.
"""

import csv
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from governiq.assurance import NewTest, record_test, rerate_residual
from governiq.models import Action, Control, Finding, User
from governiq.seed import SEED_DIR


def _rows(name: str, seed_dir: Path) -> list[dict]:
    with open(seed_dir / f"{name}.csv", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def seed_assurance(session: Session, seed_dir: Path = SEED_DIR) -> dict[str, int]:
    for row in _rows("control_tests", seed_dir):
        working_paper = (
            f"GovernIQ synthetic working paper\nControl: {row['control']}\nPeriod: {row['period']}\n"
            f"Sample size: {row['sample_size']}\nExceptions: {row['exceptions']}\nNotes: {row['notes']}\n"
        ).encode("utf-8")
        record_test(
            session,
            NewTest(
                control_code=row["control"],
                test_type=row["test_type"],
                method=row["method"],
                period=row["period"],
                sample_size=int(row["sample_size"]),
                exceptions=int(row["exceptions"]),
                performed_on=date.fromisoformat(row["performed_on"]),
                reviewer_username=row["reviewer"] or None,
                notes=row["notes"],
            ),
            actor=row["tester"],
            evidence_files=[(f"{row['control']}-{row['period']}-workpaper.txt", working_paper)],
        )

    count = 0
    for row in _rows("actions", seed_dir):
        control = session.scalar(select(Control).where(Control.code == row["control"]))
        finding = session.scalar(select(Finding).where(Finding.control_id == control.id))
        owner = session.scalar(select(User).where(User.username == row["owner"]))
        count += 1
        session.add(
            Action(
                code=f"ACT-{count:03d}",
                finding=finding,
                description=row["description"],
                owner=owner,
                due_date=date.fromisoformat(row["due_date"]),
                status=row["status"],
                completed_on=date(2026, 10, 10) if row["status"] == "Done" else None,
            )
        )
    session.commit()

    # Residual ratings go through the same rule check as the app: each risk has a proven-effective control.
    ratings = _rows("residual_ratings", seed_dir)
    for row in ratings:
        rerate_residual(
            session,
            row["risk"],
            int(row["residual_likelihood"]),
            int(row["residual_impact"]),
            row["rated_by"],
        )
    return {
        "control_tests": len(_rows("control_tests", seed_dir)),
        "actions": count,
        "residual_ratings": len(ratings),
    }
