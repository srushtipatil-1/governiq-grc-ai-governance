"""Model risk: independent validation of an AI model's performance, fairness and drift.

The metrics are computed in plain Python from synthetic hold-out and production score files, so every
number can be checked by hand. A validation run is recorded as three operating tests on the AI controls,
which means a failed metric opens a finding through the same workflow as any other control test.
"""

import bisect
import csv
import io
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from governiq.assurance import TESTER_ROLES, NewTest, record_test
from governiq.config import DATA_DIR
from governiq.models import AISystem, Control, ModelValidation, User

MODELS_DIR = DATA_DIR / "seed" / "models"

# Thresholds (the model risk appetite). The four-fifths rule (0.80) is a widely used legal floor for
# adverse impact; Kshitij Finserv's internal appetite is stricter at 0.90.
MIN_AUC = 0.70
MIN_PRECISION = 0.75
MIN_FAIRNESS_RATIO = 0.90
FOUR_FIFTHS = 0.80
MAX_TPR_GAP = 0.10
PSI_WATCH = 0.10
PSI_ACT = 0.25

PERFORMANCE_CONTROL, FAIRNESS_CONTROL, DRIFT_CONTROL = "CTL-AI-04", "CTL-AI-05", "CTL-AI-06"


@dataclass(frozen=True)
class ModelData:
    validation_file: str
    production_file: str
    production_label: str
    threshold: float  # score at or above which the model recommends approval
    label: str  # 1 = good outcome (repaid)
    groups: tuple[str, ...]


MODEL_DATA = {
    "AI-01": ModelData(
        "creditlens_validation.csv",
        "creditlens_scores_2026_09.csv",
        "September 2026",
        0.62,
        "repaid",
        ("gender", "region"),
    ),
}


@dataclass
class Check:
    area: str  # Performance, Fairness or Drift
    name: str
    value: float
    limit: str
    ok: bool
    detail: str = ""


@dataclass
class Evaluation:
    system_code: str
    sample: int
    checks: list[Check]
    group_rates: dict[str, dict[str, dict]]
    psi_bins: list[dict]
    psi: float

    def area_checks(self, area: str) -> list[Check]:
        return [c for c in self.checks if c.area == area]

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)


# ---------------------------------------------------------------- metrics (pure functions)
def auc(scores: list[float], labels: list[int]) -> float:
    """Probability that a random good case scores higher than a random bad case (ties count half)."""
    bad = sorted(s for s, y in zip(scores, labels, strict=True) if y == 0)
    good = [s for s, y in zip(scores, labels, strict=True) if y == 1]
    if not bad or not good:
        raise ValueError("AUC needs both good and bad outcomes.")
    wins = sum(
        bisect.bisect_left(bad, s) + 0.5 * (bisect.bisect_right(bad, s) - bisect.bisect_left(bad, s))
        for s in good
    )
    return wins / (len(good) * len(bad))


def confusion(scores: list[float], labels: list[int], threshold: float) -> dict[str, int]:
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for s, y in zip(scores, labels, strict=True):
        approved = s >= threshold
        counts[("t" if approved == bool(y) else "f") + ("p" if approved else "n")] += 1
    return counts


def rates(scores: list[float], labels: list[int], threshold: float) -> dict[str, float]:
    c = confusion(scores, labels, threshold)
    n = sum(c.values())
    approved = c["tp"] + c["fp"]
    good = c["tp"] + c["fn"]
    return {
        "n": n,
        "approval_rate": approved / n if n else 0.0,
        "precision": c["tp"] / approved if approved else 0.0,  # of those approved, share that repaid
        "tpr": c["tp"] / good if good else 0.0,  # of those who would repay, share approved
        "accuracy": (c["tp"] + c["tn"]) / n if n else 0.0,
    }


def psi(expected: list[float], actual: list[float], bins: int = 10) -> tuple[float, list[dict]]:
    """Population stability index using decile bins of the expected (validation) scores."""
    ordered = sorted(expected)
    edges = [ordered[int(len(ordered) * i / bins)] for i in range(1, bins)]

    def shares(values: list[float]) -> list[float]:
        counts = [0] * bins
        for v in values:
            counts[bisect.bisect_right(edges, v)] += 1
        return [max(c / len(values), 1e-4) for c in counts]  # floor avoids log(0) for empty bins

    e, a = shares(expected), shares(actual)
    table = []
    for i, (ei, ai) in enumerate(zip(e, a, strict=True)):
        low = "0.00" if i == 0 else f"{edges[i - 1]:.2f}"
        high = "1.00" if i == bins - 1 else f"{edges[i]:.2f}"
        table.append(
            {
                "bin": f"{low}-{high}",
                "expected": ei,
                "actual": ai,
                "contribution": (ai - ei) * math.log(ai / ei),
            }
        )
    return sum(row["contribution"] for row in table), table


def psi_band(value: float) -> str:
    if value > PSI_ACT:
        return "Significant shift"
    return "Moderate shift, watch" if value >= PSI_WATCH else "Stable"


# ---------------------------------------------------------------- evaluation
def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def evaluate(system_code: str, folder: Path = MODELS_DIR) -> Evaluation:
    spec = MODEL_DATA.get(system_code)
    if spec is None:
        raise ValueError(f"No validation data is configured for {system_code}.")
    rows = _read(folder / spec.validation_file)
    scores = [float(r["score"]) for r in rows]
    labels = [int(r[spec.label]) for r in rows]
    overall = rates(scores, labels, spec.threshold)
    model_auc = auc(scores, labels)
    checks = [
        Check(
            "Performance",
            "AUC",
            model_auc,
            f">= {MIN_AUC:.2f}",
            model_auc >= MIN_AUC,
            "How well scores separate repayers from defaulters (0.5 is a coin toss).",
        ),
        Check(
            "Performance",
            "Precision at threshold",
            overall["precision"],
            f">= {MIN_PRECISION:.2f}",
            overall["precision"] >= MIN_PRECISION,
            f"Of applicants approved at {spec.threshold}, the share who repaid.",
        ),
    ]

    group_rates = {}
    for attr in spec.groups:
        groups = sorted({r[attr] for r in rows})
        stats = {}
        for g in groups:
            idx = [i for i, r in enumerate(rows) if r[attr] == g]
            stats[g] = rates([scores[i] for i in idx], [labels[i] for i in idx], spec.threshold)
        group_rates[attr] = stats
        approval = {g: s["approval_rate"] for g, s in stats.items()}
        low, high = min(approval, key=approval.get), max(approval, key=approval.get)
        ratio = approval[low] / approval[high]
        checks.append(
            Check(
                "Fairness",
                f"Approval rate ratio by {attr}",
                ratio,
                f">= {MIN_FAIRNESS_RATIO:.2f}",
                ratio >= MIN_FAIRNESS_RATIO,
                f"{low} {approval[low]:.1%} vs {high} {approval[high]:.1%}. Four-fifths floor "
                f"{'met' if ratio >= FOUR_FIFTHS else 'NOT met'}.",
            )
        )
        tpr = {g: s["tpr"] for g, s in stats.items()}
        gap = max(tpr.values()) - min(tpr.values())
        checks.append(
            Check(
                "Fairness",
                f"Equal opportunity gap by {attr}",
                gap,
                f"<= {MAX_TPR_GAP:.2f}",
                gap <= MAX_TPR_GAP,
                "Difference in approval rate among applicants who did repay.",
            )
        )

    production = [float(r["score"]) for r in _read(folder / spec.production_file)]
    drift, bins = psi(scores, production)
    checks.append(
        Check(
            "Drift",
            f"PSI, {spec.production_label} vs validation",
            drift,
            f"<= {PSI_ACT:.2f}",
            drift <= PSI_ACT,
            psi_band(drift),
        )
    )
    return Evaluation(system_code, len(rows), checks, group_rates, bins, drift)


# ---------------------------------------------------------------- recording a validation
def _evidence(evaluation: Evaluation, area: str) -> tuple[str, bytes]:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["area", "check", "value", "limit", "result", "detail"])
    for c in evaluation.area_checks(area):
        writer.writerow([c.area, c.name, f"{c.value:.4f}", c.limit, "Pass" if c.ok else "Fail", c.detail])
    return f"{evaluation.system_code}-{area.lower()}-metrics.csv", buffer.getvalue().encode("utf-8")


def record_validation(
    session: Session, system_code: str, actor: str, folder: Path = MODELS_DIR, today: date | None = None
) -> ModelValidation:
    """Run the validation and record it: one operating test per area, findings opened for failures."""
    today = today or date.today()
    system = session.scalar(select(AISystem).where(AISystem.code == system_code))
    validator = session.scalar(select(User).where(User.username == actor))
    if system is None:
        raise ValueError(f"AI system '{system_code}' does not exist.")
    errors = []
    if validator is None or validator.role not in TESTER_ROLES:
        errors.append("Only a GRC Analyst or the AI Governance Lead can validate models.")
    else:
        if validator.id == system.owner_id:
            errors.append(f"{validator.full_name} owns {system.name}; validation must be independent.")
        owned = session.scalars(
            select(Control.code).where(
                Control.code.in_((PERFORMANCE_CONTROL, FAIRNESS_CONTROL, DRIFT_CONTROL)),
                Control.owner_id == validator.id,
            )
        ).all()
        if owned:
            errors.append(f"{validator.full_name} owns {', '.join(owned)}, so cannot test it (independence).")
    if errors:
        raise ValueError(" ".join(errors))

    evaluation = evaluate(system_code, folder)
    codes = []
    for area, control in (
        ("Performance", PERFORMANCE_CONTROL),
        ("Fairness", FAIRNESS_CONTROL),
        ("Drift", DRIFT_CONTROL),
    ):
        checks = evaluation.area_checks(area)
        failed = [c.name for c in checks if not c.ok]
        outcome = record_test(
            session,
            NewTest(
                control_code=control,
                test_type="Operating",
                method="Re-performance",
                period=f"Model validation {today.isoformat()}",
                sample_size=len(checks),
                exceptions=len(failed),
                performed_on=today,
                notes=f"{system.name} {area.lower()} checks on {evaluation.sample} hold-out cases. "
                + (f"Failed: {', '.join(failed)}." if failed else "All passed."),
            ),
            actor=actor,
            evidence_files=[_evidence(evaluation, area)],
        )
        codes.append(outcome.test.code)

    numbers = [int(c.split("-")[1]) for c in session.scalars(select(ModelValidation.code))]
    validation = ModelValidation(
        code=f"MV-{max(numbers, default=0) + 1:03d}",
        ai_system=system,
        validator=validator,
        run_on=today,
        result="Pass" if evaluation.passed else "Fail",
        metrics_json=json.dumps([asdict(c) for c in evaluation.checks]),
        test_codes=", ".join(codes),
    )
    session.add(validation)
    session.commit()
    return validation


def load_validations(session: Session) -> list[ModelValidation]:
    return list(
        session.scalars(
            select(ModelValidation)
            .options(selectinload(ModelValidation.ai_system), selectinload(ModelValidation.validator))
            .order_by(ModelValidation.id.desc())
        )
    )
