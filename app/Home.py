"""GovernIQ entry point. Run with: streamlit run app/Home.py

This file sets up the page, the sidebar and navigation, then runs the page the user picked.
"""

import sys
from html import escape
from pathlib import Path

# Make the 'governiq' package importable when Streamlit runs this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from governiq import __version__  # noqa: E402
from governiq.config import APP_NAME, LIVE_MODULES, MODULES  # noqa: E402
from governiq.ui import LOGO_DATA_URI, load_css  # noqa: E402

st.set_page_config(page_title=APP_NAME, page_icon=":material/link:", layout="wide")
load_css()

home = st.Page("views/home.py", title="Home", icon=":material/home:", default=True)
risk_register = st.Page(
    "views/risk_register.py", title="Risk register", icon=":material/report:", url_path="risks"
)
controls = st.Page(
    "views/controls.py", title="Controls & mapping", icon=":material/fact_check:", url_path="controls"
)
page = st.navigation([home, risk_register, controls], position="hidden")

with st.sidebar:
    st.html(
        f'<div class="giq-brand"><img src="{LOGO_DATA_URI}" width="32" height="32" alt="">'
        f"<b>{APP_NAME}</b></div>"
    )
    st.page_link(home)
    st.page_link(risk_register)
    st.page_link(controls)
    planned = "".join(
        f'<div class="giq-side-item">{escape(name)}<span>{escape(phase)}</span></div>'
        for name, phase in MODULES
        if name not in LIVE_MODULES
    )
    st.html(f'<div class="giq-side-label">Coming next</div>{planned}')
    st.html(f'<div class="giq-side-label">Version {__version__}, synthetic data only</div>')

page.run()