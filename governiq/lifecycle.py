"""AI lifecycle governance: model cards, stage gates with a go-live checklist, and post-launch reviews.

Stages run Design -> Build -> Validate -> Deployed, and any stage can be Retired. Each move is a gate:
the checks for the next stage must all pass, and the decision is recorded with the checklist as it stood.
"""

import json
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from governiq.ai_governance import ASSESSOR_ROLES, latest_assessment, load_assessments
from governiq.models import (
    AISystem,
    AuditLog,
    Finding,
    ModelCard,
    PostImplementationReview,
    Risk,
    StageGate,
    User,
)

STAGES = ("Design", "Build", "Validate", "Deployed")
NEXT_STAGE = {"Design": "Build", "Build": "Validate", "Validate": "Deployed"}
PIR_OUTCOMES = ("Continue", "Improve", "Retire")
REVIEW_EVERY_DAYS = {1: 180, 2: 365, 3: 730}  # by internal tier: stricter tier, more frequent review
DUE_SOON_DAYS = 30

# (field, label, guidance). transparency_notice is only required for systems that talk to people.
MODEL_CARD_FIELDS = (
    ("intended_use", "Intended use", "What decisions it supports, for whom, and in which process."),
    ("out_of_scope", "Out-of-scope uses", "Uses it was not designed or validated for."),
    ("training_data", "Training data", "Sources, period, personal data used and the DPDP basis."),
    ("performance", "Performance", "Validation metrics, thresholds and the date they were measured."),
    ("fairness", "Fairness", "Groups compared, the metric used and the result."),
    ("limitations", "Known limitations", "Where it is weak and what users must watch for."),
    ("human_oversight", "Human oversight", "Who reviews outputs, when, and how they can override."),
    (
        "transparency_notice",
        "Transparency notice",
        "What people are told about the AI and how to reach a human.",
    ),
)
FIELD_LABELS = {field: label for field, label, _ in MODEL_CARD_FIELDS}


def _user(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def _system(session: Session, code: str) -> AISystem:
    system = session.scalar(select(AISystem).where(AISystem.code == code))
    if system is None:
        raise ValueError(f"AI system '{code}' does not exist.")
    return system


def _log(session: Session, actor: str, action: str, entity: str, entity_id: str, after: dict) -> None:
    session.add(
        AuditLog(
            username=actor, action=action, entity=entity, entity_id=entity_id, after_json=json.dumps(after)
        )
    )


# ---------------------------------------------------------------- model cards
def card_for(session: Session, system: AISystem) -> ModelCard | None:
    return session.scalar(select(ModelCard).where(ModelCard.ai_system_id == system.id))


def missing_card_fields(system: AISystem, card: ModelCard | None) -> list[str]:
    """Labels of required fields that are empty or too thin (under 20 characters) to be useful."""
    required = [
        f for f, _, _ in MODEL_CARD_FIELDS if f != "transparency_notice" or system.interacts_with_people
    ]
    if card is None:
        return [FIELD_LABELS[f] for f in required]
    return [FIELD_LABELS[f] for f in required if len((getattr(card, f) or "").strip()) < 20]


def save_model_card(
    session: Session, system_code: str, fields: dict[str, str], actor: str, today: date | None = None
) -> ModelCard:
    """Create or update a model card. The owner writes it; the governance team can too."""
    system = _system(session, system_code)
    acting = _user(session, actor)
    if acting is None or (acting.id != system.owner_id and acting.role not in ASSESSOR_ROLES):
        raise ValueError(
            f"Only {system.owner.full_name} (the owner) or the governance team can edit this card."
        )
    unknown = set(fields) - set(FIELD_LABELS)
    if unknown:
        raise ValueError(f"Unknown model card fields: {', '.join(sorted(unknown))}.")
    card = card_for(session, system)
    if card is None:
        card = ModelCard(ai_system=system, version=1, updated_on=today or date.today(), updated_by=acting)
        session.add(card)
    else:
        if all((getattr(card, f) or "") == v.strip() for f, v in fields.items()):
            raise ValueError("Nothing changed, so no new version was saved.")
        card.version += 1
    for field, value in fields.items():
        setattr(card, field, value.strip())
    card.updated_on, card.updated_by = today or date.today(), acting
    session.flush()
    _log(session, actor, "save", "model_card", system.code, {"version": card.version})
    session.commit()
    return card


def model_card_markdown(system: AISystem, card: ModelCard) -> str:
    lines = [
        f"# Model card: {system.name} ({system.code})",
        "",
        f"Version {card.version}, updated {card.updated_on:%d %b %Y} by {card.updated_by.full_name}.  ",
        f"Owner: {system.owner.full_name}. Stage: {system.lifecycle_stage}. Model: {system.model_type}.  ",
        f"Risk tier: {system.external_tier} (internal tier {system.internal_tier}).",
        "",
    ]
    for field, label, _ in MODEL_CARD_FIELDS:
        if field == "transparency_notice" and not system.interacts_with_people:
            continue
        lines += [f"## {label}", "", (getattr(card, field) or "").strip() or "_Not written yet._", ""]
    lines.append("_Synthetic example from the GovernIQ portfolio project._")
    return "\n".join(lines)


# ---------------------------------------------------------------- gates
@dataclass
class CheckItem:
    label: str
    ok: bool
    detail: str


def open_findings_for(session: Session, system: AISystem) -> list[Finding]:
    """Open findings on any control that treats one of this system's risks."""
    risks = session.scalars(select(Risk).where(Risk.ai_system_id == system.id)).all()
    control_ids = {c.id for r in risks for c in r.controls}
    if not control_ids:
        return []
    return list(
        session.scalars(
            select(Finding)
            .where(Finding.status == "Open", Finding.control_id.in_(control_ids))
            .order_by(Finding.code)
        )
    )


def gate_checklist(session: Session, system: AISystem) -> list[CheckItem]:
    """What must be true before this system moves to its next stage. Empty when there is no next stage."""
    target = NEXT_STAGE.get(system.lifecycle_stage)
    if target is None:
        return []
    items = []
    last = latest_assessment(load_assessments(session), system)
    needs_assessment = system.internal_tier in (1, 2)
    if needs_assessment:
        items.append(
            CheckItem(
                "Risk assessment approved",
                last is not None and last.status == "Approved",
                f"{last.code} is {last.status.lower()}" if last else "No assessment yet",
            )
        )
    if target in ("Validate", "Deployed"):
        missing = missing_card_fields(system, card_for(session, system))
        items.append(
            CheckItem(
                "Model card complete",
                not missing,
                "Missing: " + ", ".join(missing) if missing else "Complete",
            )
        )
    if target == "Deployed":
        findings = open_findings_for(session, system)
        items.append(
            CheckItem(
                "No open findings on its controls",
                not findings,
                ", ".join(f"{f.code} on {f.control.code}" for f in findings) if findings else "None open",
            )
        )
        if system.external_tier == "High risk":
            items.append(
                CheckItem(
                    "Human oversight for a high-risk system",
                    system.autonomy != "Autonomous",
                    system.autonomy,
                )
            )
    return items


def advance_stage(
    session: Session, system_code: str, actor: str, note: str = "", today: date | None = None
) -> StageGate:
    today = today or date.today()
    system = _system(session, system_code)
    target = NEXT_STAGE.get(system.lifecycle_stage)
    acting = _user(session, actor)
    errors = []
    if target is None:
        raise ValueError(f"{system.name} is {system.lifecycle_stage}; there is no next stage.")
    if target == "Deployed":
        if acting is None or acting.role != "AI Governance Lead":
            errors.append("Only the AI Governance Lead can approve go-live.")
        elif acting.id == system.owner_id:
            errors.append("The system owner cannot approve their own go-live.")
    elif acting is None or acting.role not in ASSESSOR_ROLES:
        errors.append("Only a GRC Analyst or the AI Governance Lead can move a system between stages.")
    checklist = gate_checklist(session, system)
    errors += [f"{item.label}: {item.detail}." for item in checklist if not item.ok]
    if errors:
        raise ValueError(f"{system.name} cannot move to {target}. " + " ".join(errors))

    gate = StageGate(
        ai_system=system,
        from_stage=system.lifecycle_stage,
        to_stage=target,
        decided_by=acting,
        decided_on=today,
        checklist_json=json.dumps([item.__dict__ for item in checklist]),
        note=note.strip(),
    )
    system.lifecycle_stage = target
    if target == "Deployed":
        system.deployed_on = today
    session.add(gate)
    _log(session, actor, "advance", "ai_system", system.code, {"from": gate.from_stage, "to": target})
    session.commit()
    return gate


def retire_system(
    session: Session, system_code: str, actor: str, reason: str, today: date | None = None
) -> StageGate:
    system = _system(session, system_code)
    acting = _user(session, actor)
    if acting is None or acting.role != "AI Governance Lead":
        raise ValueError("Only the AI Governance Lead can retire an AI system.")
    if system.lifecycle_stage == "Retired":
        raise ValueError(f"{system.name} is already retired.")
    if len(reason.strip()) < 10:
        raise ValueError("Give the reason for retiring it in at least 10 characters.")
    gate = StageGate(
        ai_system=system,
        from_stage=system.lifecycle_stage,
        to_stage="Retired",
        decided_by=acting,
        decided_on=today or date.today(),
        note=reason.strip(),
    )
    system.lifecycle_stage = "Retired"
    session.add(gate)
    _log(session, actor, "retire", "ai_system", system.code, {"reason": reason.strip()})
    session.commit()
    return gate


# ---------------------------------------------------------------- post-implementation reviews
def reviews_for(session: Session, system: AISystem) -> list[PostImplementationReview]:
    return list(
        session.scalars(
            select(PostImplementationReview)
            .where(PostImplementationReview.ai_system_id == system.id)
            .order_by(PostImplementationReview.reviewed_on.desc())
        )
    )


def next_review_due(system: AISystem, reviews: list[PostImplementationReview]) -> date | None:
    if system.lifecycle_stage != "Deployed" or system.deployed_on is None:
        return None
    last = max([system.deployed_on, *(r.reviewed_on for r in reviews)])
    return last + timedelta(days=REVIEW_EVERY_DAYS.get(system.internal_tier, 365))


def review_status(due: date | None, today: date | None = None) -> str:
    today = today or date.today()
    if due is None:
        return "Not live"
    if due < today:
        return "Overdue"
    return "Due soon" if (due - today).days <= DUE_SOON_DAYS else "On track"


def record_review(
    session: Session, system_code: str, outcome: str, notes: str, actor: str, today: date | None = None
) -> PostImplementationReview:
    today = today or date.today()
    system = _system(session, system_code)
    acting = _user(session, actor)
    errors = []
    if system.lifecycle_stage != "Deployed":
        errors.append(f"{system.name} is not live, so there is nothing to review yet.")
    if acting is None or acting.role not in ASSESSOR_ROLES:
        errors.append("Only a GRC Analyst or the AI Governance Lead can record a post-implementation review.")
    elif acting.id == system.owner_id:
        errors.append("The system owner cannot review their own system.")
    if outcome not in PIR_OUTCOMES:
        errors.append(f"Outcome must be one of: {', '.join(PIR_OUTCOMES)}.")
    if len(notes.strip()) < 20:
        errors.append("Write at least 20 characters on what was checked and found.")
    if errors:
        raise ValueError(" ".join(errors))
    numbers = [int(c.split("-")[1]) for c in session.scalars(select(PostImplementationReview.code))]
    review = PostImplementationReview(
        code=f"PIR-{max(numbers, default=0) + 1:03d}",
        ai_system=system,
        reviewer=acting,
        reviewed_on=today,
        outcome=outcome,
        notes=notes.strip(),
    )
    session.add(review)
    session.flush()
    _log(session, actor, "review", "ai_system", system.code, {"pir": review.code, "outcome": outcome})
    session.commit()
    return review


def load_gates(session: Session) -> list[StageGate]:
    return list(session.scalars(select(StageGate).order_by(StageGate.decided_on.desc(), StageGate.id.desc())))
