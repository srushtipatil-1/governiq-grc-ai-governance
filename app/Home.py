"""GovernIQ entry point. Run with: streamlit run app/Home.py

This file sets up the page, the sidebar and navigation, then runs the page the user picked.
"""

import sys
from html import escape
from pathlib import Path

# Make the 'governiq' package importable when Streamlit runs this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402
from sqlalchemy import select  # noqa: E402

from governiq import __version__  # noqa: E402
from governiq.auth import DEMO_PASSWORD, authenticate, can, demo_mode, record_logout  # noqa: E402
from governiq.config import APP_NAME, LIVE_MODULES, MODULES  # noqa: E402
from governiq.models import User  # noqa: E402
from governiq.sign_in import render_sign_in  # noqa: E402
from governiq.ui import LOGO_DATA_URI, current_user, get_session, load_css  # noqa: E402

st.set_page_config(page_title=APP_NAME, page_icon=":material/link:", layout="wide")
load_css()

home = st.Page("views/home.py", title="Home", icon=":material/home:", default=True)
risk_register = st.Page(
    "views/risk_register.py", title="Risk register", icon=":material/report:", url_path="risks"
)
controls = st.Page(
    "views/controls.py", title="Controls & mapping", icon=":material/fact_check:", url_path="controls"
)
assurance = st.Page(
    "views/assurance.py", title="Testing & findings", icon=":material/verified:", url_path="assurance"
)
ai_governance = st.Page(
    "views/ai_governance.py", title="AI governance", icon=":material/psychology:", url_path="ai"
)
lifecycle = st.Page(
    "views/lifecycle.py", title="AI lifecycle", icon=":material/conversion_path:", url_path="lifecycle"
)
model_risk = st.Page(
    "views/model_risk.py", title="Model risk", icon=":material/query_stats:", url_path="model-risk"
)
genai = st.Page("views/genai.py", title="GenAI assurance", icon=":material/smart_toy:", url_path="genai")
audit = st.Page(
    "views/admin.py", title="Audit trail & users", icon=":material/shield_lock:", url_path="audit"
)
dashboard = st.Page(
    "views/dashboard.py", title="Dashboard", icon=":material/dashboard:", url_path="dashboard"
)
modules = [home, dashboard, risk_register, controls, assurance, ai_governance, lifecycle, model_risk, genai]

user = current_user()
if user is None:
    # Signed out: every URL still resolves (so deep links work after sign-in), but only the sign-in page runs.
    st.html(
        "<style>section[data-testid='stSidebar'], [data-testid='stSidebarCollapsedControl'] "
        "{display: none}</style>"
    )
    st.navigation([*modules, audit], position="hidden")  # resolves the URL; the page itself is not run
    render_sign_in()
    st.stop()

pages = list(modules)
if can(user.role, "verify_audit_trail"):
    pages.append(audit)
page = st.navigation(pages, position="hidden")


def _sign_out() -> None:
    with get_session() as session:
        record_logout(session, st.session_state.pop("auth_user"))


def _switch_demo_user() -> None:
    target = st.session_state["demo_switch"]
    with get_session() as session:
        record_logout(session, st.session_state["auth_user"])
        st.session_state["auth_user"] = authenticate(session, target, DEMO_PASSWORD).username


with st.sidebar:
    st.html(
        f'<div class="giq-brand"><img src="{LOGO_DATA_URI}" width="32" height="32" alt="">'
        f"<b>{APP_NAME}</b></div>"
    )
    for item in pages:
        st.page_link(item)
    planned = "".join(
        f'<div class="giq-side-item">{escape(name)}<span>{escape(phase)}</span></div>'
        for name, phase in MODULES
        if name not in LIVE_MODULES
    )
    if planned:
        st.html(f'<div class="giq-side-label">Coming next</div>{planned}')
    st.html(
        f'<div class="giq-side-label">Signed in</div><div class="giq-user"><b>{escape(user.full_name)}</b>'
        f"<span>{escape(user.role)}, {escape(user.department)}</span></div>"
    )
    if demo_mode():
        with get_session() as session:
            people = session.scalars(
                select(User).where(User.is_active).order_by(User.role, User.full_name)
            ).all()
            labels = {u.username: f"{u.full_name}, {u.role}" for u in people}
        st.selectbox(
            "Switch demo user",
            list(labels),
            index=list(labels).index(user.username),
            format_func=labels.get,
            key="demo_switch",
            on_change=_switch_demo_user,
        )
    st.button("Sign out", icon=":material/logout:", on_click=_sign_out, width="stretch")
    st.html(f'<div class="giq-side-label">Version {__version__}, synthetic data only</div>')

page.run()
