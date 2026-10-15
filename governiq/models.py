"""Database tables. One class = one table.

The shared spine: risks link to controls, controls map to framework requirements.
Cyber, privacy, vendor and AI records all attach to the same spine.
"""

from datetime import date, datetime

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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    password_hash: Mapped[str | None] = mapped_column(String(200))  # filled in Phase 11
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    """Every change in GovernIQ. Hash-chaining is added in Phase 11."""

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
    external_tier: Mapped[str | None] = mapped_column(String(20))  # set by the classifier in Phase 7
    internal_tier: Mapped[int | None] = mapped_column(Integer)

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
