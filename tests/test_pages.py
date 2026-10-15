"""Phase 4 tests: pages load from the router and the risk register works end to end."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

HOME = str(Path(__file__).resolve().parent.parent / "app" / "Home.py")


def _signed_in(username: str = "priya.analyst") -> AppTest:
    at = AppTest.from_file(HOME)
    at.session_state["auth_user"] = username
    return at.run(timeout=30)


def _open_risk_register() -> AppTest:
    at = _signed_in()
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


def _open(page: str, username: str = "priya.analyst") -> AppTest:
    at = _signed_in(username)
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


def test_assurance_page_shows_tests_and_findings(db_url):
    at = _open("views/assurance.py")
    assert not at.exception
    assert [tab.label for tab in at.tabs] == [
        "Record a test",
        "Automated checks",
        "Test log and evidence",
        "Findings and actions",
        "Residual risk",
    ]
    assert len(at.dataframe[0].value) == 5  # the automated checks catalogue
    assert len(at.dataframe[1].value) == 11  # the test log


def test_auditor_is_told_they_cannot_record_tests(db_url):
    at = AppTest.from_file(HOME)
    at.session_state["auth_user"] = "arjun.audit"
    at.run(timeout=30)
    at.switch_page("views/assurance.py").run(timeout=30)
    assert "Only a GRC Analyst" in at.info[0].value


def test_running_automated_checks_from_the_page(db_url):
    at = _open("views/assurance.py")
    [b for b in at.button if b.label == "Run checks"][0].click().run(timeout=60)
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "CCM-01**: 5 checked, 1 exception." in text
    assert "opened FND-005" in text  # CCM-02 finds the privileged account without MFA


def test_ai_governance_page_shows_inventory_and_tiers(db_url):
    at = _open("views/ai_governance.py")
    assert not at.exception
    assert [tab.label for tab in at.tabs] == [
        "AI inventory",
        "Register an AI use case",
        "Risk assessment",
        "Approvals",
    ]
    assert any("4 AI systems in the inventory" in str(h.proto) for h in at.get("html"))


def test_registering_an_ai_use_case_classifies_it(db_url):
    at = _open("views/ai_governance.py")
    [t for t in at.text_input if t.label == "Name"][0].input("HireRank")
    [t for t in at.text_input if t.label == "Purpose"][0].input("Ranks internal candidates for promotion")
    [s for s in at.selectbox if s.label == "What decisions does it support?"][0].select("Recruitment")
    [b for b in at.button if b.label == "Register and classify"][0].click().run(timeout=30)
    assert not at.exception
    assert "Registered AI-05 HireRank: High risk" in at.success[0].value


def test_submitting_an_assessment_creates_ai_risks(db_url):
    at = _open("views/ai_governance.py")
    system = [s for s in at.selectbox if s.label == "AI system"][0]
    system.select(next(o for o in system.options if "TalentSift" in o)).run(timeout=30)
    for radio in at.radio:
        if radio.key and radio.key.startswith("q-AI-04-"):
            radio.set_value("No" if radio.key.endswith("-ME2") else radio.options[0])
    [b for b in at.button if b.label == "Submit for approval"][0].click().run(timeout=30)
    assert not at.exception
    assert "Submitted AIA-002 for TalentSift. New AI risks: RSK-031." in at.success[0].value


def test_lifecycle_page_shows_gates_cards_and_reviews(db_url):
    at = _open("views/lifecycle.py")
    assert not at.exception
    assert [tab.label for tab in at.tabs] == ["Stage gates", "Model cards", "Post-launch reviews"]
    body = " ".join(str(h.proto) for h in at.get("html"))
    assert "FND-004 on CTL-AI-09" in body  # Sahayak is first in the pipeline and blocked
    assert any("FraudShield**: overdue" in m.value for m in at.markdown)


def test_blocked_go_live_explains_why(db_url):
    at = AppTest.from_file(HOME)
    at.session_state["auth_user"] = "meera.aigov"
    at.run(timeout=30)
    at.switch_page("views/lifecycle.py").run(timeout=30)
    [b for b in at.button if b.label.startswith("Move Sahayak")][0].click().run(timeout=30)
    assert "Sahayak cannot move to Deployed" in at.error[0].value


def test_model_risk_page_shows_failing_fairness_check(db_url):
    at = _open("views/model_risk.py")
    assert not at.exception
    assert [tab.label for tab in at.tabs] == ["Validation", "Fairness", "Drift", "History"]
    body = " ".join(str(h.proto) for h in at.get("html"))
    assert "6 of 7 checks pass" in body and "Approval rate ratio by gender" in body
    [b for b in at.button if b.label == "Record validation run"][0].click().run(timeout=30)
    assert "Recorded MV-001: Fail" in at.success[0].value


def test_genai_page_runs_suite_both_ways(db_url):
    at = _open("views/genai.py")
    assert not at.exception
    assert [tab.label for tab in at.tabs] == [
        "Red-team suite",
        "Try a prompt",
        "OWASP coverage",
        "Guardrails",
    ]
    assert "16 of 16 cases pass with guardrails on" in at.success[0].value
    at.toggle[0].set_value(False).run(timeout=30)
    assert "2 of 16 cases pass with guardrails off" in at.error[0].value


def test_signed_out_visitors_only_see_the_sign_in_page(db_url):
    at = AppTest.from_file(HOME).run(timeout=30)
    assert not at.exception
    assert [b.label for b in at.button if b.label.startswith("Priya")] == ["Priya Deshmukh, GRC Analyst"]
    assert not at.tabs  # no module content is rendered


def test_wrong_password_shows_a_generic_error(db_url):
    at = AppTest.from_file(HOME).run(timeout=30)
    at.text_input[0].input("priya.analyst")
    at.text_input[1].input("not-the-password-1")
    [b for b in at.button if b.label == "Sign in"][0].click().run(timeout=30)
    assert at.error[0].value == "Wrong username or password."
    assert "auth_user" not in at.session_state


def test_demo_role_button_signs_in(db_url):
    at = AppTest.from_file(HOME).run(timeout=30)
    [b for b in at.button if b.label.startswith("Arjun Rao")][0].click().run(timeout=30)
    assert at.session_state["auth_user"] == "arjun.audit"


def test_audit_page_verifies_the_chain_for_auditors(db_url):
    at = _open("views/admin.py", "arjun.audit")
    assert not at.exception
    assert "Chain verified" in at.success[0].value
    assert "Only an Admin" in at.info[0].value


def test_control_owner_has_no_audit_page(db_url):
    at = _signed_in("vikram.eng")
    assert "Audit trail & users" not in [link.label for link in at.get("page_link")]


def test_switching_demo_user_signs_in_as_them_and_is_logged(db_url, session):
    at = _signed_in("priya.analyst")
    at.selectbox(key="demo_switch").select("meera.aigov").run(timeout=30)
    assert at.session_state["auth_user"] == "meera.aigov"
    from governiq.models import AuditLog

    last_two = session.query(AuditLog.username, AuditLog.action).order_by(AuditLog.id.desc()).limit(2).all()
    assert last_two == [("meera.aigov", "login"), ("priya.analyst", "logout")]


def test_sign_out_returns_to_the_sign_in_page(db_url):
    at = _signed_in("priya.analyst")
    [b for b in at.button if b.label == "Sign out"][0].click().run(timeout=30)
    assert "auth_user" not in at.session_state
    assert any(b.label == "Sign in" for b in at.button)


def test_dashboard_shows_tiles_kris_and_downloads(db_url):
    at = _open("views/dashboard.py")
    assert not at.exception
    assert [tab.label for tab in at.tabs] == [
        "Overview",
        "Key risk indicators",
        "Committee pack",
        "Audit pack",
    ]
    body = " ".join(str(h.proto) for h in at.get("html"))
    assert "5 key risk indicators are red" in body and "Leavers whose accounts are still active" in body
    labels = [d.proto.label for d in at.get("download_button")]
    assert "Download committee pack (PDF)" in labels
    assert any(label.startswith("Download audit pack (ZIP") for label in labels)
