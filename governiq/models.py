"""Database tables. One class = one table.

The shared spine: risks link to controls, controls map to framework requirements.
Cyber, privacy, vendor and AI records all attach to the same spine.
"""

import hashlib
import itertools
import json
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from governiq.db import Base

ROLES = ("Admin", "GRC Analyst", "Control Owner", "AI Governance Lead", "Auditor")


# ---------------------------------------------------------------- People
class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(f"role IN {ROLES}", name="ck_user_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(30))
    department: Mapped[str] = mapped_column(String(50))
    password_hash: Mapped[str | None] = mapped_column(String(200))  # scrypt, see governiq.auth
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)


class AuditLog(Base):
    """Every change in GovernIQ. Each entry carries the hash of the one before it (a hash chain), so
    editing or deleting any past entry breaks the chain and governiq.audit.verify_chain reports where."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    username: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(30))
    entity: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(50))
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    entry_hash: Mapped[str | None] = mapped_column(String(64))


GENESIS_HASH = "0" * 64
_audit_order = itertools.count()


def audit_entry_hash(entry: "AuditLog") -> str:
    """SHA-256 over the previous hash and every field of the entry, in a fixed order."""
    payload = [
        entry.prev_hash,
        entry.ts.isoformat(timespec="microseconds"),
        entry.username,
        entry.action,
        entry.entity,
        entry.entity_id,
        entry.before_json,
        entry.after_json,
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()


@event.listens_for(AuditLog, "init")
def _remember_order(target, args, kwargs):
    target._order = next(_audit_order)  # sets are unordered, so remember the order entries were created


@event.listens_for(Session, "before_flush")
def _chain_new_audit_entries(session, flush_context, instances):
    new = sorted((o for o in session.new if isinstance(o, AuditLog)), key=lambda o: getattr(o, "_order", 0))
    if not new:
        return
    with session.no_autoflush:
        previous = session.scalar(select(AuditLog.entry_hash).order_by(AuditLog.id.desc()).limit(1))
    previous = previous or GENESIS_HASH
    for entry in new:
        entry.ts = entry.ts or datetime.now(UTC).replace(tzinfo=None)
        entry.prev_hash = previous
        entry.entry_hash = audit_entry_hash(entry)
        previous = entry.entry_hash


# ---------------------------------------------------------------- Frameworks
class Framework(Base):
    __tablename__ = "frameworks"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    claim_level: Mapped[str] = mapped_column(String(40))  # e.g. "Partial mapping"

    requirements: Mapped[list["Requirement"]] = relationship(back_populates="framework")


class Requirement(Base):
    """One clause or control of a framework. Titles are our own short paraphrases."""

    __tablename__ = "requirements"
    __table_args__ = (UniqueConstraint("framework_id", "ref", name="uq_requirement_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    framework_id: Mapped[int] = mapped_column(ForeignKey("frameworks.id"))
    ref: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))

    framework: Mapped[Framework] = relationship(back_populates="requirements")


control_requirement_map = Table(
    "control_requirement_map",
    Base.metadata,
    Column("control_id", ForeignKey("controls.id"), primary_key=True),
    Column("requirement_id", ForeignKey("requirements.id"), primary_key=True),
)

risk_controls = Table(
    "risk_controls",
    Base.metadata,
    Column("risk_id", ForeignKey("risks.id"), primary_key=True),
    Column("control_id", ForeignKey("controls.id"), primary_key=True),
)


class Control(Base):
    """An internal control. One control can satisfy requirements in several frameworks."""

    __tablename__ = "controls"
    __table_args__ = (
        CheckConstraint("control_type IN ('Preventive', 'Detective', 'Corrective')", name="ck_ctl_type"),
        CheckConstraint("nature IN ('Manual', 'Automated')", name="ck_ctl_nature"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(40))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    control_type: Mapped[str] = mapped_column(String(20))
    nature: Mapped[str] = mapped_column(String(20))
    frequency: Mapped[str] = mapped_column(String(20))
    is_key: Mapped[bool] = mapped_column(Boolean, default=False)

    owner: Mapped[User] = relationship()
    requirements: Mapped[list[Requirement]] = relationship(secondary=control_requirement_map)


# ---------------------------------------------------------------- Things we protect
class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    asset_type: Mapped[str] = mapped_column(String(40))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    holds_personal_data: Mapped[bool] = mapped_column(Boolean)
    criticality: Mapped[str] = mapped_column(String(10))

    owner: Mapped[User] = relationship()


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    service: Mapped[str] = mapped_column(String(150))
    criticality: Mapped[str] = mapped_column(String(10))
    is_ai_provider: Mapped[bool] = mapped_column(Boolean)
    has_soc2_report: Mapped[bool] = mapped_column(Boolean)
    certificate_expiry: Mapped[date | None] = mapped_column(Date)


class AISystem(Base):
    __tablename__ = "ai_systems"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_stage IN ('Design', 'Build', 'Validate', 'Deployed', 'Retired')", name="ck_ai_stage"
        ),
        CheckConstraint(
            "autonomy IN ('Human in the loop', 'Human on the loop', 'Autonomous')", name="ck_ai_autonomy"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(String(250))
    model_type: Mapped[str] = mapped_column(String(80))
    build_type: Mapped[str] = mapped_column(String(30))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uses_personal_data: Mapped[bool] = mapped_column(Boolean)
    people_affected: Mapped[int] = mapped_column(Integer)
    decides_on_individuals: Mapped[bool] = mapped_column(Boolean)
    autonomy: Mapped[str] = mapped_column(String(30))
    lifecycle_stage: Mapped[str] = mapped_column(String(20))
    domain: Mapped[str] = mapped_column(String(40), default="Other")  # what decisions the system supports
    interacts_with_people: Mapped[bool] = mapped_column(Boolean, default=False)
    external_tier: Mapped[str | None] = mapped_column(String(20))  # set by governiq.ai_governance.classify
    internal_tier: Mapped[int | None] = mapped_column(Integer)
    tier_reasons: Mapped[str | None] = mapped_column(Text)  # why the classifier chose these tiers
    deployed_on: Mapped[date | None] = mapped_column(Date)  # set when the go-live gate is passed

    vendor: Mapped[Vendor | None] = relationship()
    owner: Mapped[User] = relationship()


# ---------------------------------------------------------------- Risk register
class Risk(Base):
    __tablename__ = "risks"
    __table_args__ = (
        CheckConstraint("likelihood BETWEEN 1 AND 5", name="ck_risk_likelihood"),
        CheckConstraint("impact BETWEEN 1 AND 5", name="ck_risk_impact"),
        CheckConstraint(
            "residual_likelihood IS NULL OR residual_likelihood BETWEEN 1 AND 5", name="ck_risk_res_l"
        ),
        CheckConstraint("residual_impact IS NULL OR residual_impact BETWEEN 1 AND 5", name="ck_risk_res_i"),
        CheckConstraint("treatment IN ('Mitigate', 'Transfer', 'Avoid', 'Accept')", name="ck_risk_treatment"),
        CheckConstraint("status IN ('Open', 'In treatment', 'Closed')", name="ck_risk_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(30), default="Manual")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"))
    ai_system_id: Mapped[int | None] = mapped_column(ForeignKey("ai_systems.id"))
    likelihood: Mapped[int] = mapped_column(Integer)
    impact: Mapped[int] = mapped_column(Integer)
    residual_likelihood: Mapped[int | None] = mapped_column(Integer)
    residual_impact: Mapped[int | None] = mapped_column(Integer)
    treatment: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="Open")
    due_date: Mapped[date] = mapped_column(Date)

    owner: Mapped[User] = relationship()
    asset: Mapped[Asset | None] = relationship()
    vendor: Mapped[Vendor | None] = relationship()
    ai_system: Mapped[AISystem | None] = relationship()
    controls: Mapped[list[Control]] = relationship(secondary=risk_controls)

    @property
    def inherent_score(self) -> int:
        return self.likelihood * self.impact


# ---------------------------------------------------------------- Assurance: tests, evidence, findings
class ControlTest(Base):
    """One test of one control. The result is derived from the exceptions, never typed in."""

    __tablename__ = "control_tests"
    __table_args__ = (
        CheckConstraint("test_type IN ('Design', 'Operating')", name="ck_test_type"),
        CheckConstraint(
            "method IN ('Inquiry', 'Inspection', 'Observation', 'Re-performance', 'Automated')",
            name="ck_test_method",
        ),
        CheckConstraint("sample_size >= 1", name="ck_test_sample"),
        CheckConstraint("exceptions BETWEEN 0 AND sample_size", name="ck_test_exceptions"),
        CheckConstraint("result IN ('Effective', 'Ineffective')", name="ck_test_result"),
        CheckConstraint(
            "reviewer_id IS NULL OR reviewer_id != tester_id", name="ck_test_reviewer_not_tester"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("controls.id"))
    test_type: Mapped[str] = mapped_column(String(20))
    method: Mapped[str] = mapped_column(String(20))
    period: Mapped[str] = mapped_column(String(20))
    sample_size: Mapped[int] = mapped_column(Integer)
    exceptions: Mapped[int] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(20))
    tester_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    performed_on: Mapped[date] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")

    control: Mapped[Control] = relationship()
    tester: Mapped[User] = relationship(foreign_keys=[tester_id])
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewer_id])
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="test")


class Evidence(Base):
    """A file supporting a test. The SHA-256 fingerprint proves it has not changed since upload."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("control_tests.id"))
    filename: Mapped[str] = mapped_column(String(200))  # the name the user uploaded
    stored_name: Mapped[str] = mapped_column(String(80), unique=True)  # random name on disk
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_on: Mapped[date] = mapped_column(Date)

    test: Mapped[ControlTest] = relationship(back_populates="evidence")
    uploaded_by: Mapped[User] = relationship()


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint("severity IN ('High', 'Medium', 'Low')", name="ck_finding_severity"),
        CheckConstraint("status IN ('Open', 'Closed')", name="ck_finding_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("controls.id"))
    test_id: Mapped[int] = mapped_column(ForeignKey("control_tests.id"))
    title: Mapped[str] = mapped_column(String(250))
    severity: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="Open")
    raised_on: Mapped[date] = mapped_column(Date)
    closed_on: Mapped[date | None] = mapped_column(Date)
    closed_by_test_id: Mapped[int | None] = mapped_column(ForeignKey("control_tests.id"))

    control: Mapped[Control] = relationship()
    test: Mapped[ControlTest] = relationship(foreign_keys=[test_id])
    actions: Mapped[list["Action"]] = relationship(back_populates="finding")


class Action(Base):
    """A corrective action that fixes a finding."""

    __tablename__ = "actions"
    __table_args__ = (CheckConstraint("status IN ('Open', 'Done')", name="ck_action_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"))
    description: Mapped[str] = mapped_column(String(300))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), default="Open")
    completed_on: Mapped[date | None] = mapped_column(Date)

    finding: Mapped[Finding] = relationship(back_populates="actions")
    owner: Mapped[User] = relationship()


# ---------------------------------------------------------------- AI governance
class AIAssessment(Base):
    """A NIST AI RMF-structured risk and impact assessment of one AI system."""

    __tablename__ = "ai_assessments"
    __table_args__ = (
        CheckConstraint("status IN ('Submitted', 'Approved', 'Rejected')", name="ck_aia_status"),
        CheckConstraint(
            "approver_id IS NULL OR approver_id != assessor_id", name="ck_aia_approver_not_assessor"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    ai_system_id: Mapped[int] = mapped_column(ForeignKey("ai_systems.id"))
    assessor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="Submitted")
    answers_json: Mapped[str] = mapped_column(Text)
    submitted_on: Mapped[date] = mapped_column(Date)
    decided_on: Mapped[date | None] = mapped_column(Date)
    decision_note: Mapped[str] = mapped_column(Text, default="")

    ai_system: Mapped[AISystem] = relationship()
    assessor: Mapped[User] = relationship(foreign_keys=[assessor_id])
    approver: Mapped[User | None] = relationship(foreign_keys=[approver_id])


# ---------------------------------------------------------------- AI lifecycle
class ModelCard(Base):
    """Plain-language documentation of one AI system, kept with a version number."""

    __tablename__ = "model_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    ai_system_id: Mapped[int] = mapped_column(ForeignKey("ai_systems.id"), unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    intended_use: Mapped[str] = mapped_column(Text, default="")
    out_of_scope: Mapped[str] = mapped_column(Text, default="")
    training_data: Mapped[str] = mapped_column(Text, default="")
    performance: Mapped[str] = mapped_column(Text, default="")
    fairness: Mapped[str] = mapped_column(Text, default="")
    limitations: Mapped[str] = mapped_column(Text, default="")
    human_oversight: Mapped[str] = mapped_column(Text, default="")
    transparency_notice: Mapped[str] = mapped_column(Text, default="")
    updated_on: Mapped[date] = mapped_column(Date)
    updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    ai_system: Mapped[AISystem] = relationship()
    updated_by: Mapped[User] = relationship()


class StageGate(Base):
    """A decision to move an AI system to its next lifecycle stage, with the checklist as it stood."""

    __tablename__ = "stage_gates"

    id: Mapped[int] = mapped_column(primary_key=True)
    ai_system_id: Mapped[int] = mapped_column(ForeignKey("ai_systems.id"))
    from_stage: Mapped[str] = mapped_column(String(20))
    to_stage: Mapped[str] = mapped_column(String(20))
    decided_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_on: Mapped[date] = mapped_column(Date)
    checklist_json: Mapped[str] = mapped_column(Text, default="[]")
    note: Mapped[str] = mapped_column(Text, default="")

    ai_system: Mapped[AISystem] = relationship()
    decided_by: Mapped[User] = relationship()


class PostImplementationReview(Base):
    """A periodic check that a live AI system still does what it was approved to do."""

    __tablename__ = "post_implementation_reviews"
    __table_args__ = (CheckConstraint("outcome IN ('Continue', 'Improve', 'Retire')", name="ck_pir_outcome"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    ai_system_id: Mapped[int] = mapped_column(ForeignKey("ai_systems.id"))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reviewed_on: Mapped[date] = mapped_column(Date)
    outcome: Mapped[str] = mapped_column(String(10))
    notes: Mapped[str] = mapped_column(Text)

    ai_system: Mapped[AISystem] = relationship()
    reviewer: Mapped[User] = relationship()


# ---------------------------------------------------------------- Model risk
class ModelValidation(Base):
    """An independent validation run: performance, fairness and drift metrics, recorded as control tests."""

    __tablename__ = "model_validations"
    __table_args__ = (CheckConstraint("result IN ('Pass', 'Fail')", name="ck_mv_result"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    ai_system_id: Mapped[int] = mapped_column(ForeignKey("ai_systems.id"))
    validator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    run_on: Mapped[date] = mapped_column(Date)
    result: Mapped[str] = mapped_column(String(10))
    metrics_json: Mapped[str] = mapped_column(Text)
    test_codes: Mapped[str] = mapped_column(String(100))

    ai_system: Mapped[AISystem] = relationship()
    validator: Mapped[User] = relationship()
