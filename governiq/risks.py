"""Risk register logic: scoring, rating bands, validation and queries.

Implements docs/risk-methodology.md. The Streamlit pages only display what these functions return,
so every rule here is tested without a browser.
"""

import json
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from governiq.models import AuditLog, Control, Risk, User

CATEGORIES = ("Cyber", "Privacy", "Third party", "AI", "Operational")
TREATMENTS = ("Mitigate", "Transfer", "Avoid", "Accept")
RATINGS = ("Critical", "High", "Medium", "Low")

# (lowest score, rating) checked from the top down. Matches the methodology table.
RATING_BANDS = ((20, "Critical"), (10, "High"), (5, "Medium"), (1, "Low"))


def score(likelihood: int, impact: int) -> int:
    for name, value in (("Likelihood", likelihood), ("Impact", impact)):
        if not 1 <= value <= 5:
            raise ValueError(f"{name} must be between 1 and 5, got {value}")
    return likelihood * impact


def rating_for(risk_score: int) -> str:
    for lowest, rating in RATING_BANDS:
        if risk_score >= lowest:
            return rating
    raise ValueError(f"Score must be between 1 and 25, got {risk_score}")


def residual_errors(
    inherent: int, residual_likelihood: int, residual_impact: int, has_effective_control: bool
) -> list[str]:
    """Return the methodology rules a proposed residual rating breaks (empty list = acceptable)."""
    residual = score(residual_likelihood, residual_impact)
    errors = []
    if residual > inherent:
        errors.append(f"Residual score {residual} cannot be higher than inherent score {inherent}.")
    if residual < inherent and not has_effective_control:
        errors.append(
            "Residual risk can only be lower than inherent risk when a linked control "
            "has passed its latest operating effectiveness test."
        )
    return errors


@dataclass
class NewRisk:
    title: str
    category: str
    owner_username: str
    likelihood: int
    impact: int
    treatment: str
    due_date: date
    control_codes: list[str] = field(default_factory=list)


def validate_new_risk(data: NewRisk, today: date | None = None) -> list[str]:
    today = today or date.today()
    errors = []
    title = data.title.strip()
    if not 10 <= len(title) <= 200:
        errors.append("Title must be between 10 and 200 characters.")
    if data.category not in CATEGORIES:
        errors.append(f"Category must be one of: {', '.join(CATEGORIES)}.")
    if data.treatment not in TREATMENTS:
        errors.append(f"Treatment must be one of: {', '.join(TREATMENTS)}.")
    for name, value in (("Likelihood", data.likelihood), ("Impact", data.impact)):
        if not 1 <= value <= 5:
            errors.append(f"{name} must be between 1 and 5.")
    if data.due_date <= today:
        errors.append("Due date must be in the future.")
    if data.treatment in ("Mitigate", "Transfer") and not data.control_codes:
        errors.append("Link at least one control when the treatment is Mitigate or Transfer.")
    return errors


def next_risk_code(session: Session) -> str:
    codes = session.scalars(select(Risk.code)).all()
    numbers = [int(code.split("-")[1]) for code in codes if code.startswith("RSK-")]
    return f"RSK-{max(numbers, default=0) + 1:03d}"


def create_risk(session: Session, data: NewRisk, actor: str) -> Risk:
    """Validate, save and log a new risk. Raises ValueError listing every problem found."""
    errors = validate_new_risk(data)
    owner = session.scalar(select(User).where(User.username == data.owner_username))
    if owner is None:
        errors.append(f"Owner '{data.owner_username}' does not exist.")
    controls = session.scalars(select(Control).where(Control.code.in_(data.control_codes))).all()
    missing = set(data.control_codes) - {c.code for c in controls}
    if missing:
        errors.append(f"Unknown control(s): {', '.join(sorted(missing))}.")
    if errors:
        raise ValueError(" ".join(errors))

    risk = Risk(
        code=next_risk_code(session),
        title=data.title.strip(),
        category=data.category,
        owner=owner,
        likelihood=data.likelihood,
        impact=data.impact,
        treatment=data.treatment,
        due_date=data.due_date,
        controls=list(controls),
    )
    session.add(risk)
    session.flush()
    session.add(
        AuditLog(
            username=actor,
            action="create",
            entity="risk",
            entity_id=risk.code,
            after_json=json.dumps(
                {
                    "title": risk.title,
                    "category": risk.category,
                    "owner": data.owner_username,
                    "likelihood": risk.likelihood,
                    "impact": risk.impact,
                    "treatment": risk.treatment,
                    "due_date": risk.due_date.isoformat(),
                    "controls": sorted(data.control_codes),
                }
            ),
        )
    )
    session.commit()
    return risk


def load_risks(session: Session) -> list[Risk]:
    query = (
        select(Risk)
        .options(
            selectinload(Risk.owner),
            selectinload(Risk.ai_system),
            selectinload(Risk.controls).selectinload(Control.requirements),
        )
        .order_by(Risk.code)
    )
    return list(session.scalars(query))


def risk_rows(risks: list[Risk]) -> list[dict]:
    """Flatten risks into table rows for display and export."""
    rows = []
    for risk in risks:
        inherent = risk.inherent_score
        rows.append(
            {
                "Code": risk.code,
                "Risk": risk.title,
                "Category": risk.category,
                "Owner": risk.owner.full_name,
                "L": risk.likelihood,
                "I": risk.impact,
                "Score": inherent,
                "Rating": rating_for(inherent),
                "Treatment": risk.treatment,
                "Controls": len(risk.controls),
                "Due": risk.due_date,
                "Status": risk.status,
            }
        )
    return rows


def heatmap_counts(risks: list[Risk]) -> dict[tuple[int, int], int]:
    """Number of risks in each (likelihood, impact) cell of the 5x5 matrix."""
    counts = {(likelihood, impact): 0 for likelihood in range(1, 6) for impact in range(1, 6)}
    for risk in risks:
        counts[(risk.likelihood, risk.impact)] += 1
    return counts


def rating_summary(risks: list[Risk]) -> dict[str, int]:
    summary = dict.fromkeys(RATINGS, 0)
    for risk in risks:
        summary[rating_for(risk.inherent_score)] += 1
    return summary
