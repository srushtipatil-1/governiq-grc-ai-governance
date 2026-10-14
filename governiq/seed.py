"""Load the synthetic Kshitij Finserv data from data/seed/*.csv into the database."""

import csv
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from governiq.config import DATA_DIR
from governiq.models import AISystem, Asset, Control, Framework, Requirement, Risk, User, Vendor

SEED_DIR = DATA_DIR / "seed"


def _rows(name: str, seed_dir: Path) -> list[dict]:
    with open(seed_dir / f"{name}.csv", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _yes(value: str) -> bool:
    return value.strip().lower() == "yes"


def _lookup(table: dict, key: str, what: str):
    """Find a record by its code, or stop with a clear message naming the bad value."""
    if key not in table:
        raise ValueError(f"Seed data refers to unknown {what} '{key}'")
    return table[key]


def seed(session: Session, seed_dir: Path = SEED_DIR) -> dict[str, int]:
    """Insert all seed data. Returns how many records of each kind were created."""
    users = {r["username"]: User(**r) for r in _rows("users", seed_dir)}
    session.add_all(users.values())

    assets = {}
    for r in _rows("assets", seed_dir):
        assets[r["code"]] = Asset(
            code=r["code"],
            name=r["name"],
            asset_type=r["asset_type"],
            owner=_lookup(users, r["owner"], "user"),
            holds_personal_data=_yes(r["holds_personal_data"]),
            criticality=r["criticality"],
        )
    session.add_all(assets.values())

    vendors = {}
    for r in _rows("vendors", seed_dir):
        expiry = r["certificate_expiry"]
        vendors[r["code"]] = Vendor(
            code=r["code"],
            name=r["name"],
            service=r["service"],
            criticality=r["criticality"],
            is_ai_provider=_yes(r["is_ai_provider"]),
            has_soc2_report=_yes(r["has_soc2_report"]),
            certificate_expiry=date.fromisoformat(expiry) if expiry else None,
        )
    session.add_all(vendors.values())

    ai_systems = {}
    for r in _rows("ai_systems", seed_dir):
        ai_systems[r["code"]] = AISystem(
            code=r["code"],
            name=r["name"],
            purpose=r["purpose"],
            model_type=r["model_type"],
            build_type=r["build_type"],
            vendor=_lookup(vendors, r["vendor"], "vendor") if r["vendor"] else None,
            owner=_lookup(users, r["owner"], "user"),
            uses_personal_data=_yes(r["uses_personal_data"]),
            people_affected=int(r["people_affected"]),
            decides_on_individuals=_yes(r["decides_on_individuals"]),
            autonomy=r["autonomy"],
            lifecycle_stage=r["lifecycle_stage"],
        )
    session.add_all(ai_systems.values())

    frameworks = {r["code"]: Framework(**r) for r in _rows("frameworks", seed_dir)}
    session.add_all(frameworks.values())

    requirements = {}
    for r in _rows("requirements", seed_dir):
        key = f"{r['framework']}:{r['ref']}"
        requirements[key] = Requirement(
            framework=_lookup(frameworks, r["framework"], "framework"), ref=r["ref"], title=r["title"]
        )
    session.add_all(requirements.values())

    controls = {}
    for r in _rows("controls", seed_dir):
        controls[r["code"]] = Control(
            code=r["code"],
            title=r["title"],
            domain=r["domain"],
            owner=_lookup(users, r["owner"], "user"),
            control_type=r["control_type"],
            nature=r["nature"],
            frequency=r["frequency"],
            is_key=_yes(r["is_key"]),
            requirements=[_lookup(requirements, k, "requirement") for k in r["maps_to"].split(";")],
        )
    session.add_all(controls.values())

    risks = []
    for r in _rows("risks", seed_dir):
        risks.append(
            Risk(
                code=r["code"],
                title=r["title"],
                category=r["category"],
                owner=_lookup(users, r["owner"], "user"),
                asset=_lookup(assets, r["asset"], "asset") if r["asset"] else None,
                vendor=_lookup(vendors, r["vendor"], "vendor") if r["vendor"] else None,
                ai_system=_lookup(ai_systems, r["ai_system"], "AI system") if r["ai_system"] else None,
                likelihood=int(r["likelihood"]),
                impact=int(r["impact"]),
                treatment=r["treatment"],
                due_date=date.fromisoformat(r["due_date"]),
                controls=[_lookup(controls, c, "control") for c in r["controls"].split(";")],
            )
        )
    session.add_all(risks)
    session.commit()

    return {
        "users": len(users),
        "assets": len(assets),
        "vendors": len(vendors),
        "ai_systems": len(ai_systems),
        "frameworks": len(frameworks),
        "requirements": len(requirements),
        "controls": len(controls),
        "risks": len(risks),
    }