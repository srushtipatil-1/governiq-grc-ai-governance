"""Phase 4 tests: pages load from the router and the risk register works end to end."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

HOME = str(Path(__file__).resolve().parent.parent / "app" / "Home.py")


def _open_risk_register() -> AppTest:
    at = AppTest.from_file(HOME).run(timeout=30)
    return at.switch_page("views/risk_register.py").run(timeout=30)


def test_risk_register_loads_all_risks(db_url):
    at = _open_risk_register()
    assert not at.exception
    assert [tab.label for tab in at.tabs] == ["Register", "Heat map", "Trace a risk", "Add a risk"]
    assert len(at.dataframe[0].value) == 30


def test_category_filter_narrows_the_register(db_url):
    at = _open_risk_register()
    at.multiselect[0].select("AI").run(timeout=30)
    shown = at.dataframe[0].value
    assert len(shown) == 11
    assert set(shown["Category"]) == {"AI"}


def test_adding_a_valid_risk_through_the_form(db_url):
    at = _open_risk_register()
    [t for t in at.text_input if t.label == "Risk title"][0].input(
        "Loan officers export customer lists to USB drives"
    )
    controls = [m for m in at.multiselect if m.label == "Linked controls"][0]
    controls.select(next(option for option in controls.options if option.startswith("CTL-OPS-05")))
    [b for b in at.button if b.label == "Add risk"][0].click().run(timeout=30)
    assert not at.exception
    assert "Added RSK-031" in at.success[0].value
    assert len(at.dataframe[0].value) == 31  # the page reloaded, so the register already shows the new risk


def test_form_explains_why_a_risk_is_rejected(db_url):
    at = _open_risk_register()
    [t for t in at.text_input if t.label == "Risk title"][0].input("Too short")
    [b for b in at.button if b.label == "Add risk"][0].click().run(timeout=30)
    assert "Risk not added" in at.error[0].value
    assert "Title must be between 10 and 200 characters" in at.error[0].value


def _open(page: str) -> AppTest:
    at = AppTest.from_file(HOME).run(timeout=30)
    return at.switch_page(page).run(timeout=30)


def test_controls_page_shows_library_coverage_and_rcm(db_url):
    at = _open("views/controls.py")
    assert not at.exception
    assert [tab.label for tab in at.tabs] == [
        "Control library",
        "Framework coverage",
        "Crosswalk",
        "Risk & control matrix",
    ]
    assert len(at.dataframe[0].value) == 33  # control library
    assert "13 requirements with no control yet" in " ".join(m.value for m in at.markdown)


def test_framework_filter_narrows_the_control_library(db_url):
    at = _open("views/controls.py")
    [m for m in at.multiselect if m.label == "Framework"][0].select("OWASP LLM").run(timeout=30)
    assert set(at.dataframe[0].value["Code"]) == {"CTL-AI-09", "CTL-AI-10"}
