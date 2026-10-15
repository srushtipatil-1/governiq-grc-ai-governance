"""Shared Streamlit helpers: styling, the database session and the GovernIQ logo."""

import base64
from pathlib import Path

import streamlit as st
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from governiq.config import PROJECT_ROOT
from governiq.db import create_tables, database_url, make_engine, make_session_factory
from governiq.models import User
from governiq.seed import seed
from governiq.seed_assurance import seed_assurance

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
        if session.scalar(select(func.count()).select_from(User)) == 0:
            seed(session)  # first run anywhere (e.g. a fresh cloud deployment) gets the demo data
            seed_assurance(session)
    return engine


def get_session() -> Session:
    return make_session_factory(_engine(database_url()))()


DEFAULT_ACTOR = "priya.analyst"


def current_actor() -> str:
    """The demo user the visitor is acting as. Real login with passwords arrives in Phase 11."""
    return st.session_state.get("actor", DEFAULT_ACTOR)
