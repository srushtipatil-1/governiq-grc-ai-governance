"""Central settings. Later phases read the database path and app name from here."""

from pathlib import Path

APP_NAME = "GovernIQ"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "governiq.db"
EVIDENCE_DIR = DATA_DIR / "evidence"  # uploaded evidence files; kept out of Git by .gitignore

DISCLAIMER = (
    "Educational portfolio project using synthetic data. "
    "It is not a certification, a conformity assessment, or proof that any "
    "organisation complies with ISO/IEC 27001, ISO/IEC 42001, NIST, DPDP or any other framework."
)

MODULES = [
    ("Risk Register", "Phase 4"),
    ("Controls & Framework Mapping", "Phase 5"),
    ("Evidence, Findings & Actions", "Phase 6"),
    ("AI Governance", "Phase 7"),
    ("AI Lifecycle & Model Cards", "Phase 8"),
    ("Model Risk Validation", "Phase 9"),
    ("GenAI Assurance", "Phase 10"),
    ("Dashboards & Audit Pack", "Phase 12"),
]

# Modules that are built, tested and clickable in the app.
LIVE_MODULES = {
    "Risk Register",
    "Controls & Framework Mapping",
    "Evidence, Findings & Actions",
    "AI Governance",
    "AI Lifecycle & Model Cards",
    "Model Risk Validation",
    "GenAI Assurance",
    "Dashboards & Audit Pack",
}

# Short display names for framework codes.
FRAMEWORK_LABELS = {
    "ISO27001": "ISO 27001",
    "NISTCSF": "NIST CSF",
    "DPDP": "DPDP",
    "ISO42001": "ISO 42001",
    "NISTAIRMF": "NIST AI RMF",
    "RBIFREEAI": "RBI FREE-AI",
    "OWASPLLM": "OWASP LLM",
}
