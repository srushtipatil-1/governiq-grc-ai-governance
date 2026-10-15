"""Assurance logic: control testing, hashed evidence, findings, corrective actions and residual risk.

Rules enforced here (see docs/roles-and-access.md and docs/risk-methodology.md):
- Only GRC Analysts and the AI Governance Lead test controls, and never a control they own.
- The reviewer must be someone other than the tester and the control owner.
- The test result comes from the exceptions found; nobody types "Effective".
- A failed test opens a finding. A finding closes only when all its actions are done
  AND a later operating test of the same control passes.
- Residual risk can drop below inherent only when a linked control's latest operating test passed.
"""

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from governiq.config import EVIDENCE_DIR
from governiq.models import Action, AuditLog, Control, ControlTest, Evidence, Finding, Risk, User
from governiq.risks import residual_errors

TESTER_ROLES = ("GRC Analyst", "AI Governance Lead")
TEST_TYPES = ("Design", "Operating")
METHODS = ("Inquiry", "Inspection", "Observation", "Re-performance", "Automated")
ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".csv", ".docx", ".txt", ".png", ".jpg", ".jpeg"}
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------- helpers
def evidence_dir() -> Path:
    """Where evidence files live. Tests point this at a temporary folder."""
    folder = Path(os.environ.get("GOVERNIQ_EVIDENCE_DIR", EVIDENCE_DIR))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _next_code(session: Session, column, prefix: str, width: int = 3) -> str:
    numbers = [int(code.rsplit("-", 1)[1]) for code in session.scalars(select(column)) if code]
    return f"{prefix}-{max(numbers, default=0) + 1:0{width}d}"


def _user(session: Session, username: str | None) -> User | None:
    if not username:
        return None
    return session.scalar(select(User).where(User.username == username))


def _log(session: Session, actor: str, action: str, entity: str, entity_id: str, before=None, after=None):
    session.add(
        AuditLog(
            username=actor,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before_json=json.dumps(before) if before is not None else None,
            after_json=json.dumps(after) if after is not None else None,
        )
    )


# ---------------------------------------------------------------- evidence
def evidence_errors(filename: str, data: bytes) -> list[str]:
    errors = []
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        errors.append(f"'{filename}': file type {extension or '(none)'} is not allowed.")
    if len(data) == 0:
        errors.append(f"'{filename}': the file is empty.")
    if len(data) > MAX_EVIDENCE_BYTES:
        errors.append(f"'{filename}': larger than 10 MB.")
    return errors


def _store_evidence(
    session: Session, test: ControlTest, filename: str, data: bytes, uploader: User
) -> Evidence:
    """Save the file under a random name (never the user's name) and record its fingerprint."""
    stored_name = uuid.uuid4().hex + Path(filename).suffix.lower()
    (evidence_dir() / stored_name).write_bytes(data)
    evidence = Evidence(
        code=_next_code(session, Evidence.code, "EV", 4),
        test=test,
        filename=Path(filename).name,
        stored_name=stored_name,
        sha256=sha256_of(data),
        size_bytes=len(data),
        uploaded_by=uploader,
        uploaded_on=date.today(),
    )
    session.add(evidence)
    session.flush()
    return evidence


def verify_evidence(evidence: Evidence) -> bool:
    """True when the stored file still matches the fingerprint taken at upload."""
    path = evidence_dir() / evidence.stored_name
    return path.exists() and sha256_of(path.read_bytes()) == evidence.sha256


# ---------------------------------------------------------------- testing
@dataclass
class NewTest:
    control_code: str
    test_type: str
    method: str
    period: str
    sample_size: int
    exceptions: int
    performed_on: date
    reviewer_username: str | None = None
    notes: str = ""


def check_new_test(session: Session, data: NewTest, tester: User | None, evidence_count: int) -> list[str]:
    errors = []
    control = session.scalar(select(Control).where(Control.code == data.control_code))
    if control is None:
        return [f"Control '{data.control_code}' does not exist."]
    if tester is None or tester.role not in TESTER_ROLES:
        errors.append("Only a GRC Analyst or the AI Governance Lead can record control tests.")
    elif tester.id == control.owner_id:
        errors.append(f"{tester.full_name} owns {control.code}, so cannot test it (independence).")
    reviewer = _user(session, data.reviewer_username)
    if data.reviewer_username and reviewer is None:
        errors.append(f"Reviewer '{data.reviewer_username}' does not exist.")
    if reviewer is not None:
        if tester is not None and reviewer.id == tester.id:
            errors.append("The reviewer must be a different person from the tester.")
        if reviewer.id == control.owner_id:
            errors.append("The control owner cannot review the test of their own control.")
        if reviewer.role in ("Admin", "Auditor"):
            errors.append("Admins and auditors cannot review tests.")
    if data.test_type not in TEST_TYPES:
        errors.append("Test type must be Design or Operating.")
    if data.method not in METHODS:
        errors.append(f"Method must be one of: {', '.join(METHODS)}.")
    if data.test_type == "Design" and data.sample_size != 1:
        errors.append("A test of design is a walkthrough of one item, so the sample size must be 1.")
    if data.sample_size < 1:
        errors.append("Sample size must be at least 1.")
    if not 0 <= data.exceptions <= data.sample_size:
        errors.append("Exceptions must be between 0 and the sample size.")
    if data.performed_on > date.today():
        errors.append("The test date cannot be in the future.")
    if not data.period.strip():
        errors.append("Enter the period tested, for example 2026-Q3.")
    if evidence_count == 0:
        errors.append("Attach at least one evidence file. A test without evidence cannot be relied on.")
    return errors


@dataclass
class RecordedTest:
    test: ControlTest
    opened: Finding | None
    closed: list[Finding]
    still_open: list[Finding]


def record_test(
    session: Session, data: NewTest, actor: str, evidence_files: list[tuple[str, bytes]]
) -> RecordedTest:
    """Validate and save a test with its evidence, then open or close findings as the rules require."""
    tester = _user(session, actor)
    errors = check_new_test(session, data, tester, len(evidence_files))
    for filename, content in evidence_files:
        errors += evidence_errors(filename, content)
    if errors:
        raise ValueError(" ".join(errors))

    control = session.scalar(select(Control).where(Control.code == data.control_code))
    test = ControlTest(
        code=_next_code(session, ControlTest.code, "TST"),
        control=control,
        test_type=data.test_type,
        method=data.method,
        period=data.period.strip(),
        sample_size=data.sample_size,
        exceptions=data.exceptions,
        result="Effective" if data.exceptions == 0 else "Ineffective",
        tester=tester,
        reviewer=_user(session, data.reviewer_username),
        performed_on=data.performed_on,
        notes=data.notes.strip(),
    )
    session.add(test)
    session.flush()
    for filename, content in evidence_files:
        _store_evidence(session, test, filename, content, tester)

    open_findings = session.scalars(
        select(Finding).where(Finding.control_id == control.id, Finding.status == "Open")
    ).all()
    opened, closed, still_open = None, [], []
    if test.result == "Ineffective" and not open_findings:
        opened = Finding(
            code=_next_code(session, Finding.code, "FND"),
            control=control,
            test=test,
            title=(
                f"{control.title}: {data.exceptions} of {data.sample_size} "
                f"{'items' if data.sample_size > 1 else 'item'} failed ({data.test_type.lower()} test)"
            ),
            severity="High" if control.is_key else "Medium",
            raised_on=data.performed_on,
        )
        session.add(opened)
        session.flush()
        _log(
            session,
            actor,
            "open",
            "finding",
            opened.code,
            after={"test": test.code, "severity": opened.severity},
        )
    elif test.result == "Effective" and test.test_type == "Operating":
        for finding in open_findings:
            if finding.actions and all(a.status == "Done" for a in finding.actions):
                finding.status, finding.closed_on, finding.closed_by_test_id = (
                    "Closed",
                    data.performed_on,
                    test.id,
                )
                closed.append(finding)
                _log(session, actor, "close", "finding", finding.code, after={"retest": test.code})
            else:
                still_open.append(finding)

    _log(
        session,
        actor,
        "create",
        "control_test",
        test.code,
        after={
            "control": control.code,
            "type": test.test_type,
            "sample": test.sample_size,
            "exceptions": test.exceptions,
            "result": test.result,
            "evidence": [e.sha256 for e in test.evidence],
        },
    )
    session.commit()
    return RecordedTest(test, opened, closed, still_open)


# ---------------------------------------------------------------- findings and actions
def add_action(
    session: Session, finding_code: str, description: str, owner_username: str, due_date: date, actor: str
) -> Action:
    errors = []
    acting = _user(session, actor)
    if acting is None or acting.role not in TESTER_ROLES:
        errors.append("Only a GRC Analyst or the AI Governance Lead can assign corrective actions.")
    finding = session.scalar(select(Finding).where(Finding.code == finding_code))
    if finding is None:
        errors.append(f"Finding '{finding_code}' does not exist.")
    elif finding.status == "Closed":
        errors.append(f"{finding_code} is already closed.")
    owner = _user(session, owner_username)
    if owner is None or owner.role in ("Admin", "Auditor"):
        errors.append("Choose an action owner who is not an admin or auditor.")
    if len(description.strip()) < 10:
        errors.append("Describe the action in at least 10 characters.")
    if due_date <= date.today():
        errors.append("The due date must be in the future.")
    if errors:
        raise ValueError(" ".join(errors))

    action = Action(
        code=_next_code(session, Action.code, "ACT"),
        finding=finding,
        description=description.strip(),
        owner=owner,
        due_date=due_date,
    )
    session.add(action)
    session.flush()
    _log(
        session,
        actor,
        "create",
        "action",
        action.code,
        after={"finding": finding_code, "owner": owner_username},
    )
    session.commit()
    return action


def complete_action(session: Session, action_code: str, actor: str) -> Action:
    action = session.scalar(select(Action).where(Action.code == action_code))
    acting = _user(session, actor)
    if action is None:
        raise ValueError(f"Action '{action_code}' does not exist.")
    if acting is None or (acting.id != action.owner_id and acting.role not in TESTER_ROLES):
        raise ValueError("Only the action owner or a GRC Analyst can mark this action done.")
    if action.status == "Done":
        raise ValueError(f"{action_code} is already done.")
    action.status, action.completed_on = "Done", date.today()
    _log(
        session, actor, "complete", "action", action_code, before={"status": "Open"}, after={"status": "Done"}
    )
    session.commit()
    return action


# ---------------------------------------------------------------- control status and residual risk
def latest_operating_results(session: Session) -> dict[str, ControlTest]:
    """The most recent operating test for each tested control, keyed by control code."""
    tests = session.scalars(
        select(ControlTest)
        .where(ControlTest.test_type == "Operating")
        .options(selectinload(ControlTest.control))
        .order_by(ControlTest.performed_on, ControlTest.id)
    )
    return {test.control.code: test for test in tests}


def effective_controls(session: Session) -> set[str]:
    return {code for code, test in latest_operating_results(session).items() if test.result == "Effective"}


def rerate_residual(session: Session, risk_code: str, likelihood: int, impact: int, actor: str) -> Risk:
    acting = _user(session, actor)
    if acting is None or acting.role not in TESTER_ROLES:
        raise ValueError("Only a GRC Analyst or the AI Governance Lead can re-rate residual risk.")
    risk = session.scalar(select(Risk).where(Risk.code == risk_code))
    if risk is None:
        raise ValueError(f"Risk '{risk_code}' does not exist.")
    working = effective_controls(session)
    has_effective = any(control.code in working for control in risk.controls)
    errors = residual_errors(risk.inherent_score, likelihood, impact, has_effective)
    if errors:
        raise ValueError(" ".join(errors))
    before = {"residual_likelihood": risk.residual_likelihood, "residual_impact": risk.residual_impact}
    risk.residual_likelihood, risk.residual_impact = likelihood, impact
    _log(
        session,
        actor,
        "rerate",
        "risk",
        risk_code,
        before=before,
        after={"residual_likelihood": likelihood, "residual_impact": impact},
    )
    session.commit()
    return risk


# ---------------------------------------------------------------- queries for the pages
def load_tests(session: Session) -> list[ControlTest]:
    return list(
        session.scalars(
            select(ControlTest)
            .options(
                selectinload(ControlTest.control),
                selectinload(ControlTest.tester),
                selectinload(ControlTest.reviewer),
                selectinload(ControlTest.evidence),
            )
            .order_by(ControlTest.performed_on.desc(), ControlTest.id.desc())
        )
    )


def load_findings(session: Session) -> list[Finding]:
    return list(
        session.scalars(
            select(Finding)
            .options(
                selectinload(Finding.control).selectinload(Control.owner),
                selectinload(Finding.actions).selectinload(Action.owner),
                selectinload(Finding.test),
            )
            .order_by(Finding.status.desc(), Finding.code)
        )
    )
