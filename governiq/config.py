"""Central settings. Later phases read the database path and app name from here."""

from pathlib import Path

APP_NAME = "GovernIQ"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "governiq.db"

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
    ("Model Risk & GenAI Assurance", "Phase 9-10"),
    ("Dashboards & Audit Pack", "Phase 12"),
]