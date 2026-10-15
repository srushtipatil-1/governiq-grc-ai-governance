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
from governiq.config import APP_NAME, LIVE_MODULES, MODULES  # noqa: E402
from governiq.models import User  # noqa: E402
from governiq.ui import DEFAULT_ACTOR, LOGO_DATA_URI, get_session, load_css  # noqa: E402

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
page = st.navigation([home, risk_register, controls, assurance, ai_governance, lifecycle], position="hidden")

with st.sidebar:
    st.html(
        f'<div class="giq-brand"><img src="{LOGO_DATA_URI}" width="32" height="32" alt="">'
        f"<b>{APP_NAME}</b></div>"
    )
    st.page_link(home)
    st.page_link(risk_register)
    st.page_link(controls)
    st.page_link(assurance)
    st.page_link(ai_governance)
    st.page_link(lifecycle)
    planned = "".join(
        f'<div class="giq-side-item">{escape(name)}<span>{escape(phase)}</span></div>'
        for name, phase in MODULES
        if name not in LIVE_MODULES
    )
    st.html(f'<div class="giq-side-label">Coming next</div>{planned}')
    with get_session() as session:
        people = session.scalars(select(User).order_by(User.role, User.full_name)).all()
        labels = {u.username: f"{u.full_name}, {u.role}" for u in people}
    st.html('<div class="giq-side-label">Acting as (demo, no password until Phase 11)</div>')
    st.selectbox(
        "Acting as",
        list(labels),
        index=list(labels).index(st.session_state.get("actor", DEFAULT_ACTOR)),
        format_func=labels.get,
        key="actor",
        label_visibility="collapsed",
    )
    st.html(f'<div class="giq-side-label">Version {__version__}, synthetic data only</div>')

page.run()
