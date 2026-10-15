"""AI governance logic: inventory intake, risk tiering and the NIST AI RMF-structured assessment.

Tiering is rule-based on purpose, so every tier comes with
the reasons that produced it. It is a classification method inspired by the EU AI Act, not legal advice.
"""

import json
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from governiq.models import AIAssessment, AISystem, AuditLog, Risk, User, Vendor
from governiq.risks import NewRisk, create_risk

ASSESSOR_ROLES = ("GRC Analyst", "AI Governance Lead")
AUTONOMY_LEVELS = ("Human in the loop", "Human on the loop", "Autonomous")
BUILD_TYPES = ("Built in-house", "Bought", "Built on third-party API")

PROHIBITED_DOMAINS = {
    "Social scoring": "social scoring of individuals is a prohibited practice",
    "Emotion recognition at work": "emotion recognition in the workplace is a prohibited practice",
}
HIGH_RISK_DOMAINS = {
    "Credit decisions": "decides on the creditworthiness of individuals (an Annex III high-risk use)",
    "Recruitment": "screens or ranks job candidates (an Annex III high-risk use)",
    "Education access": "decides on access to education (an Annex III high-risk use)",
    "Insurance pricing": "prices life or health insurance for individuals (an Annex III high-risk use)",
}
OTHER_DOMAINS = ("Fraud detection", "Customer service", "Marketing", "Internal productivity", "Other")
DOMAINS = (*HIGH_RISK_DOMAINS, *OTHER_DOMAINS, *PROHIBITED_DOMAINS)


# ---------------------------------------------------------------- classification
def classify(
    domain: str,
    interacts_with_people: bool,
    uses_personal_data: bool,
    people_affected: int,
    decides_on_individuals: bool,
    autonomy: str,
) -> tuple[str, int, list[str]]:
    """Return (external tier, internal tier 1-3, reasons). Rules are checked in order; first match wins."""
    reasons = []
    if domain in PROHIBITED_DOMAINS:
        external = "Prohibited"
        reasons.append(f"Prohibited: {PROHIBITED_DOMAINS[domain]}.")
    elif domain in HIGH_RISK_DOMAINS:
        external = "High risk"
        reasons.append(f"High risk: {HIGH_RISK_DOMAINS[domain]}.")
    elif interacts_with_people:
        external = "Limited risk"
        reasons.append("Limited risk: talks to people directly, so they must be told it is AI.")
    else:
        external = "Minimal risk"
        reasons.append("Minimal risk: no listed high-risk use and no direct interaction with people.")
        if domain == "Fraud detection":
            reasons.append("Fraud detection is carved out of the credit-scoring high-risk use.")

    points = 0
    if uses_personal_data:
        points += 1
        reasons.append("Internal +1: uses personal data (DPDP applies).")
    if people_affected > 10_000:
        points += 1
        reasons.append(f"Internal +1: affects {people_affected:,} people.")
    if decides_on_individuals:
        points += 1
        reasons.append("Internal +1: makes or shapes decisions about individuals.")
    if autonomy == "Autonomous":
        points += 1
        reasons.append("Internal +1: acts without a human reviewing each output.")
    if external in ("Prohibited", "High risk") or points >= 3:
        internal = 1
    elif points >= 1:
        internal = 2
    else:
        internal = 3
    reasons.append(f"Internal tier {internal} ({points} risk factor{'s' if points != 1 else ''}).")
    return external, internal, reasons


def apply_classification(system: AISystem) -> None:
    external, internal, reasons = classify(
        system.domain,
        system.interacts_with_people,
        system.uses_personal_data,
        system.people_affected,
        system.decides_on_individuals,
        system.autonomy,
    )
    system.external_tier, system.internal_tier, system.tier_reasons = external, internal, "\n".join(reasons)


# ---------------------------------------------------------------- intake
@dataclass
class NewAISystem:
    name: str
    purpose: str
    domain: str
    model_type: str
    build_type: str
    owner_username: str
    vendor_code: str | None
    uses_personal_data: bool
    people_affected: int
    decides_on_individuals: bool
    interacts_with_people: bool
    autonomy: str


def _user(session: Session, username: str | None) -> User | None:
    return session.scalar(select(User).where(User.username == username)) if username else None


def _log(session: Session, actor: str, action: str, entity: str, entity_id: str, after: dict) -> None:
    session.add(
        AuditLog(
            username=actor, action=action, entity=entity, entity_id=entity_id, after_json=json.dumps(after)
        )
    )


def register_ai_system(session: Session, data: NewAISystem, actor: str) -> AISystem:
    errors = []
    acting = _user(session, actor)
    if acting is None or acting.role not in ASSESSOR_ROLES:
        errors.append("Only a GRC Analyst or the AI Governance Lead can register AI systems.")
    if not 3 <= len(data.name.strip()) <= 60:
        errors.append("Name must be 3 to 60 characters.")
    if session.scalar(select(AISystem).where(AISystem.name == data.name.strip())):
        errors.append(f"An AI system called '{data.name.strip()}' is already registered.")
    if len(data.purpose.strip()) < 15:
        errors.append("Describe the purpose in at least 15 characters.")
    if data.domain not in DOMAINS:
        errors.append("Choose a domain from the list.")
    if data.build_type not in BUILD_TYPES:
        errors.append("Choose how the system is built or bought.")
    if data.autonomy not in AUTONOMY_LEVELS:
        errors.append("Choose the level of human oversight.")
    if data.people_affected < 0:
        errors.append("People affected cannot be negative.")
    owner = _user(session, data.owner_username)
    if owner is None or owner.role in ("Admin", "Auditor"):
        errors.append("Choose a business owner who is not an admin or auditor.")
    vendor = None
    if data.build_type != "Built in-house":
        vendor = (
            session.scalar(select(Vendor).where(Vendor.code == data.vendor_code))
            if data.vendor_code
            else None
        )
        if vendor is None:
            errors.append("A bought or API-based system needs its vendor.")
    if errors:
        raise ValueError(" ".join(errors))

    numbers = [int(c.split("-")[1]) for c in session.scalars(select(AISystem.code))]
    system = AISystem(
        code=f"AI-{max(numbers, default=0) + 1:02d}",
        name=data.name.strip(),
        purpose=data.purpose.strip(),
        model_type=data.model_type.strip() or "Not stated",
        build_type=data.build_type,
        vendor=vendor,
        owner=owner,
        uses_personal_data=data.uses_personal_data,
        people_affected=data.people_affected,
        decides_on_individuals=data.decides_on_individuals,
        interacts_with_people=data.interacts_with_people,
        autonomy=data.autonomy,
        lifecycle_stage="Design",
        domain=data.domain,
    )
    apply_classification(system)
    session.add(system)
    session.flush()
    _log(
        session,
        actor,
        "register",
        "ai_system",
        system.code,
        {"name": system.name, "external_tier": system.external_tier, "internal_tier": system.internal_tier},
    )
    if system.external_tier == "Prohibited":
        session.rollback()
        raise ValueError(
            f"Not registered. {system.tier_reasons.splitlines()[0]} It cannot be built or bought."
        )
    session.commit()
    return system


# ---------------------------------------------------------------- assessment questionnaire
@dataclass(frozen=True)
class Question:
    id: str
    function: str  # NIST AI RMF function
    characteristic: str  # NIST AI RMF trustworthiness characteristic
    text: str
    gap: str  # how the risk is described when the answer is No or Partial
    control: str
    important: bool = True
    allow_na: bool = False


QUESTIONS = (
    Question(
        "G1",
        "Govern",
        "Accountable and transparent",
        "Is a named business owner accountable for the system?",
        "no accountable owner",
        "CTL-AI-02",
    ),
    Question(
        "G2",
        "Govern",
        "Accountable and transparent",
        "Is it in the AI inventory with its purpose, data and owner?",
        "missing from the AI inventory",
        "CTL-AI-02",
    ),
    Question(
        "G3",
        "Govern",
        "Accountable and transparent",
        "Does it follow the board-approved AI policy?",
        "AI policy not applied",
        "CTL-AI-01",
        important=False,
    ),
    Question(
        "G4",
        "Govern",
        "Secure and resilient",
        "For a vendor model, is the vendor assessed and are AI clauses in the contract?",
        "vendor and contract not assessed",
        "CTL-TPR-01",
        allow_na=True,
    ),
    Question(
        "M1",
        "Map",
        "Valid and reliable",
        "Are the intended purpose and the uses it must not be put to written down?",
        "purpose and limits not documented",
        "CTL-AI-03",
        important=False,
    ),
    Question(
        "M2",
        "Map",
        "Safe",
        "Have the people affected and the possible harms to them been identified?",
        "impact on people not assessed",
        "CTL-AI-03",
    ),
    Question(
        "M3",
        "Map",
        "Privacy-enhanced",
        "Is personal data limited to what the purpose needs, with a DPIA where required?",
        "personal data use not minimised or assessed",
        "CTL-PRV-01",
    ),
    Question(
        "M4",
        "Map",
        "Accountable and transparent",
        "Is there a defined human oversight step for decisions that affect people?",
        "no defined human oversight",
        "CTL-AI-07",
    ),
    Question(
        "ME1",
        "Measure",
        "Valid and reliable",
        "Was accuracy validated independently before deployment?",
        "accuracy not independently validated",
        "CTL-AI-04",
    ),
    Question(
        "ME2",
        "Measure",
        "Fair with harmful bias managed",
        "Has fairness been tested across groups such as gender and region?",
        "fairness across groups not tested",
        "CTL-AI-05",
    ),
    Question(
        "ME3",
        "Measure",
        "Valid and reliable",
        "Are performance and drift monitored in production?",
        "performance and drift not monitored",
        "CTL-AI-06",
    ),
    Question(
        "ME4",
        "Measure",
        "Secure and resilient",
        "For an LLM, has it been tested for prompt injection and data leakage?",
        "not tested for prompt injection or data leakage",
        "CTL-AI-09",
        allow_na=True,
    ),
    Question(
        "MA1",
        "Manage",
        "Explainable and interpretable",
        "Are people told when AI is involved in a decision or conversation about them?",
        "people not told AI is involved",
        "CTL-AI-08",
        important=False,
    ),
    Question(
        "MA2",
        "Manage",
        "Accountable and transparent",
        "Can affected people ask for a human review?",
        "no route to a human review",
        "CTL-AI-07",
    ),
    Question(
        "MA3",
        "Manage",
        "Safe",
        "Is there a tested way to switch the system off or roll it back?",
        "cannot be switched off or rolled back safely",
        "CTL-AI-11",
    ),
    Question(
        "MA4",
        "Manage",
        "Accountable and transparent",
        "Are AI incidents logged, investigated and reported?",
        "AI incidents not tracked",
        "CTL-AI-11",
        important=False,
    ),
)
QUESTIONS_BY_ID = {q.id: q for q in QUESTIONS}
FUNCTIONS = ("Govern", "Map", "Measure", "Manage")
ANSWERS = ("Yes", "Partial", "No", "Not applicable")
ANSWER_SCORE = {"Yes": 1.0, "Partial": 0.5, "No": 0.0}


def function_scores(answers: dict[str, str]) -> dict[str, int]:
    """Percentage score per NIST AI RMF function, ignoring 'Not applicable' answers."""
    scores = {}
    for function in FUNCTIONS:
        values = [
            ANSWER_SCORE[answers[q.id]]
            for q in QUESTIONS
            if q.function == function and answers.get(q.id) in ANSWER_SCORE
        ]
        scores[function] = round(100 * sum(values) / len(values)) if values else 100
    return scores


@dataclass
class SubmittedAssessment:
    assessment: AIAssessment
    risks_created: list[Risk]


def submit_assessment(
    session: Session, system_code: str, answers: dict[str, str], actor: str, today: date | None = None
) -> SubmittedAssessment:
    """Save an assessment. Each No or Partial on an important question becomes a risk in the register."""
    today = today or date.today()
    errors = []
    acting = _user(session, actor)
    system = session.scalar(select(AISystem).where(AISystem.code == system_code))
    if system is None:
        raise ValueError(f"AI system '{system_code}' does not exist.")
    if acting is None or acting.role not in ASSESSOR_ROLES:
        errors.append("Only a GRC Analyst or the AI Governance Lead can assess AI systems.")
    elif acting.id == system.owner_id:
        errors.append(f"{acting.full_name} owns {system.name}, so cannot assess it (independence).")
    missing = [q.id for q in QUESTIONS if q.id not in answers]
    if missing:
        errors.append(f"Answer every question (missing: {', '.join(missing)}).")
    for qid, answer in answers.items():
        question = QUESTIONS_BY_ID.get(qid)
        if question is None or answer not in ANSWERS:
            errors.append(f"Invalid answer for {qid}.")
        elif answer == "Not applicable" and not question.allow_na:
            errors.append(f"{qid} applies to every system, so 'Not applicable' is not allowed.")
    pending = session.scalar(
        select(AIAssessment).where(AIAssessment.ai_system_id == system.id, AIAssessment.status == "Submitted")
    )
    if pending:
        errors.append(f"{pending.code} for {system.name} is still waiting for a decision.")
    if errors:
        raise ValueError(" ".join(errors))

    numbers = [int(c.split("-")[1]) for c in session.scalars(select(AIAssessment.code))]
    assessment = AIAssessment(
        code=f"AIA-{max(numbers, default=0) + 1:03d}",
        ai_system=system,
        assessor=acting,
        answers_json=json.dumps(answers),
        submitted_on=today,
    )
    session.add(assessment)
    session.flush()
    _log(
        session,
        actor,
        "submit",
        "ai_assessment",
        assessment.code,
        {"system": system.code, **function_scores(answers)},
    )
    session.commit()

    created = []
    for question in QUESTIONS:
        answer = answers[question.id]
        if not question.important or answer not in ("No", "Partial"):
            continue
        title = f"{system.name}: {question.gap}"
        if session.scalar(select(Risk).where(Risk.title == title)):
            continue  # already in the register from an earlier assessment
        risk = create_risk(
            session,
            NewRisk(
                title=title,
                category="AI",
                owner_username=system.owner.username,
                likelihood=4 if answer == "No" else 3,
                impact=5 if system.decides_on_individuals else 4,
                treatment="Mitigate",
                due_date=today + timedelta(days=30),
                control_codes=[question.control],
            ),
            actor=actor,
        )
        risk.ai_system, risk.source = system, f"AI assessment {assessment.code}"
        session.commit()
        created.append(risk)
    return SubmittedAssessment(assessment, created)


def decide_assessment(session: Session, code: str, approve: bool, note: str, actor: str) -> AIAssessment:
    errors = []
    acting = _user(session, actor)
    assessment = session.scalar(select(AIAssessment).where(AIAssessment.code == code))
    if assessment is None:
        raise ValueError(f"Assessment '{code}' does not exist.")
    if acting is None or acting.role != "AI Governance Lead":
        errors.append("Only the AI Governance Lead can approve or reject AI assessments.")
    else:
        if acting.id == assessment.assessor_id:
            errors.append("The approver must be a different person from the assessor.")
        if acting.id == assessment.ai_system.owner_id:
            errors.append("The system owner cannot approve the assessment of their own system.")
    if assessment.status != "Submitted":
        errors.append(f"{code} has already been {assessment.status.lower()}.")
    if not approve and len(note.strip()) < 10:
        errors.append("Explain the rejection in at least 10 characters.")
    if errors:
        raise ValueError(" ".join(errors))
    assessment.status = "Approved" if approve else "Rejected"
    assessment.approver, assessment.decided_on, assessment.decision_note = acting, date.today(), note.strip()
    _log(session, actor, assessment.status.lower(), "ai_assessment", code, {"note": note.strip()})
    session.commit()
    return assessment


# ---------------------------------------------------------------- queries
def load_ai_systems(session: Session) -> list[AISystem]:
    return list(
        session.scalars(
            select(AISystem)
            .options(selectinload(AISystem.owner), selectinload(AISystem.vendor))
            .order_by(AISystem.code)
        )
    )


def load_assessments(session: Session) -> list[AIAssessment]:
    return list(
        session.scalars(
            select(AIAssessment)
            .options(
                selectinload(AIAssessment.ai_system),
                selectinload(AIAssessment.assessor),
                selectinload(AIAssessment.approver),
            )
            .order_by(AIAssessment.code.desc())
        )
    )


def latest_assessment(assessments: list[AIAssessment], system: AISystem) -> AIAssessment | None:
    mine = [a for a in assessments if a.ai_system_id == system.id]
    return max(mine, key=lambda a: a.id) if mine else None
