"""Shared Streamlit helpers: styling, the database session and the GovernIQ logo."""

import base64
from pathlib import Path

import streamlit as st
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from governiq.config import PROJECT_ROOT
from governiq.db import create_tables, database_url, make_engine, make_session_factory
from governiq.demo import rebuild_demo_data
from governiq.models import User

CSS_FILE = PROJECT_ROOT / "app" / "assets" / "style.css"

_LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="8" fill="#E8A33D"/>'
    '<rect x="6" y="11" width="12" height="10" rx="5" fill="none" stroke="#14213D" stroke-width="2.5"/>'
    '<rect x="14" y="11" width="12" height="10" rx="5" fill="none" stroke="#14213D" stroke-width="2.5"/>'
    "</svg>"
)
LOGO_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode()).decode()


def load_css(css_file: Path = CSS_FILE) -> None:
    st.html(f"<style>{css_file.read_text(encoding='utf-8')}</style>")


@st.cache_resource
def _engine(url: str) -> Engine:
    """One engine per database URL, created once and reused across page reruns."""
    engine = make_engine(url)
    create_tables(engine)
    with make_session_factory(engine)() as session:
        empty = session.scalar(select(func.count()).select_from(User)) == 0
    if empty:
        rebuild_demo_data(engine)  # first run anywhere (e.g. a fresh cloud deployment) gets the demo data
    return engine


def demo_engine() -> Engine:
    return _engine(database_url())


def get_session() -> Session:
    return make_session_factory(_engine(database_url()))()


def current_actor() -> str | None:
    """Username of the signed-in user, or None when signed out. Set only by the sign-in page."""
    return st.session_state.get("auth_user")


def current_user() -> User | None:
    username = current_actor()
    if username is None:
        return None
    with get_session() as session:
        user = session.scalar(select(User).where(User.username == username, User.is_active))
        if user is not None:
            session.expunge(user)
        return user
