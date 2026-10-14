"""Phase 1 smoke tests: the package imports and the home page renders."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

import governiq
from governiq.config import DISCLAIMER, MODULES

HOME = Path(__file__).resolve().parent.parent / "app" / "Home.py"


def test_version_is_set():
    assert governiq.__version__ == "0.2.0"


def test_disclaimer_rules_out_compliance_claims():
    assert "not a certification" in DISCLAIMER


def test_six_modules_planned():
    assert len(MODULES) == 6


def test_home_page_renders_without_errors():
    at = AppTest.from_file(str(HOME)).run(timeout=30)
    assert not at.exception
    page_html = " ".join(element.proto.body for element in at.get("html"))
    assert "GovernIQ" in page_html
    assert "Risk Register" in page_html
    assert "not a certification" in page_html
