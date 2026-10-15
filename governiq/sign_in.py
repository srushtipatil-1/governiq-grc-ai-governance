"""Sign-in screen, shown in place of any page while signed out.

Every attempt, good or bad, is written to the hash-chained audit trail."""

from html import escape

import streamlit as st
from sqlalchemy import select

from governiq.auth import DEMO_PASSWORD, authenticate, demo_mode
from governiq.config import APP_NAME, DISCLAIMER
from governiq.models import User
from governiq.ui import LOGO_DATA_URI, get_session

DEMO_ACCOUNTS = (
    ("priya.analyst", "Test controls, run checks, assess AI"),
    ("meera.aigov", "Approve AI assessments and go-live"),
    ("vikram.eng", "Own controls, systems and actions"),
    ("arjun.audit", "Read everything, verify the audit trail"),
    ("admin.demo", "Manage users and passwords"),
)


def render_sign_in() -> None:
    session = get_session()

    def _sign_in(username: str, password: str) -> None:
        try:
            user = authenticate(session, username, password)
        except ValueError as problem:
            st.session_state["login_error"] = str(problem)
        else:
            st.session_state["auth_user"] = user.username
            st.session_state.pop("login_error", None)

    left, _, right = st.columns([1.15, 0.1, 1])
    with left:
        st.html(
            f"""
            <div class="giq-login-hero">
              <div class="giq-login-brand">
                <img src="{LOGO_DATA_URI}" width="32" height="32" alt="">{APP_NAME}</div>
              <h1>GRC and AI governance on one spine.</h1>
              <p>Risks, controls, evidence, findings, AI assessments, model validation and LLM red-teaming
              for a fictional Indian NBFC, all traced to proof.</p>
              <ul>
                <li><b>ROLES</b>Five roles with segregation of duties enforced in code</li>
                <li><b>AUDIT</b>Every change in a hash-chained, tamper-evident audit trail</li>
                <li><b>DATA</b>Synthetic data only; nothing real is stored</li>
              </ul>
            </div>
            """
        )
    with right:
        with st.container(border=True):
            st.markdown("#### Sign in")
            with st.form("sign_in", border=False):
                username = st.text_input("Username", autocomplete="username")
                password = st.text_input("Password", type="password", autocomplete="current-password")
                submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
            if submitted:
                _sign_in(username, password)
                if "auth_user" in st.session_state:
                    st.rerun()
            if "login_error" in st.session_state:
                st.error(st.session_state["login_error"], icon=":material/lock:")

        if demo_mode():
            names = {u.username: u for u in session.scalars(select(User))}
            st.markdown("**Try a demo role**")
            st.caption(
                f"All demo accounts use the password `{DEMO_PASSWORD}`. Five wrong attempts lock an account."
            )
            for username, what in DEMO_ACCOUNTS:
                account = names.get(username)
                if account is None:
                    continue
                if st.button(
                    f"{account.full_name}, {account.role}",
                    key=f"demo-{username}",
                    help=escape(what),
                    width="stretch",
                ):
                    _sign_in(username, DEMO_PASSWORD)
                    st.rerun()

    st.caption(DISCLAIMER)
