"""Risk register: every risk scored with the 5x5 method, traced to its controls."""

from datetime import date, timedelta
from html import escape

import pandas as pd
import streamlit as st
from sqlalchemy import select

from governiq.config import FRAMEWORK_LABELS
from governiq.models import Control, User
from governiq.risks import (
    CATEGORIES,
    RATINGS,
    TREATMENTS,
    NewRisk,
    create_risk,
    heatmap_counts,
    load_risks,
    rating_for,
    rating_summary,
    risk_rows,
)
from governiq.ui import current_actor, get_session

RATING_CLASS = {"Critical": "crit", "High": "high", "Medium": "med", "Low": "low"}
RATING_STYLE = {
    "Critical": "background-color:#F6DDE0;color:#8E2433;font-weight:600",
    "High": "background-color:#FBEBD2;color:#8A5A12;font-weight:600",
    "Medium": "background-color:#F3EFD9;color:#6B5E1E;font-weight:600",
    "Low": "background-color:#DCEFEA;color:#17605A;font-weight:600",
}

session = get_session()
risks = load_risks(session)
summary = rating_summary(risks)

# ---------- Header and rating distribution ----------
segments = "".join(
    f'<div class="giq-dist-seg {RATING_CLASS[r]}" style="flex:{summary[r]}"></div>'
    for r in RATINGS
    if summary[r]
)
legend = "".join(
    f'<span><i class="giq-swatch {RATING_CLASS[r]}"></i>{r} <b>{summary[r]}</b></span>' for r in RATINGS
)
st.html(
    f"""
    <div class="giq-page-head">
      <h1>Risk register</h1>
      <p>{len(risks)} risks across cyber, privacy, third party and AI, each scored as
      likelihood &times; impact and rated with the bands in the risk methodology.</p>
    </div>
    <div class="giq-dist" role="img" aria-label="Risks by inherent rating">{segments}</div>
    <div class="giq-dist-legend">{legend}</div>
    """
)

register_tab, heatmap_tab, trace_tab, add_tab = st.tabs(
    ["Register", "Heat map", "Trace a risk", "Add a risk"]
)

# ---------- Register ----------
with register_tab:
    table = pd.DataFrame(risk_rows(risks))
    left, middle, right = st.columns([2, 2, 3])
    chosen_categories = left.multiselect("Category", CATEGORIES, placeholder="All categories")
    chosen_ratings = middle.multiselect("Inherent rating", RATINGS, placeholder="All ratings")
    search = right.text_input("Search", placeholder="Search by code, title or owner")

    view = table
    if chosen_categories:
        view = view[view["Category"].isin(chosen_categories)]
    if chosen_ratings:
        view = view[view["Rating"].isin(chosen_ratings)]
    if search:
        text = view["Code"] + " " + view["Risk"] + " " + view["Owner"]
        view = view[text.str.contains(search, case=False, regex=False)]

    view = view.sort_values(["Score", "Code"], ascending=[False, True])
    st.caption(f"Showing {len(view)} of {len(table)} risks, highest score first.")
    st.dataframe(
        view.style.map(lambda rating: RATING_STYLE.get(rating, ""), subset=["Rating"]),
        hide_index=True,
        width="stretch",
        column_config={
            "Risk": st.column_config.TextColumn(width="large"),
            "L": st.column_config.NumberColumn(help="Likelihood, 1 to 5"),
            "I": st.column_config.NumberColumn(help="Impact, 1 to 5"),
            "Score": st.column_config.NumberColumn(help="Inherent score = L x I"),
            "Due": st.column_config.DateColumn(format="D MMM YYYY"),
        },
    )
    st.download_button(
        "Download register as CSV",
        view.to_csv(index=False).encode("utf-8"),
        file_name=f"governiq-risk-register-{date.today().isoformat()}.csv",
        mime="text/csv",
        icon=":material/download:",
    )

# ---------- Heat map ----------
with heatmap_tab:
    counts = heatmap_counts(risks)
    cells = ""
    for likelihood in range(5, 0, -1):
        cells += f'<div class="giq-hm-axis">{likelihood}</div>'
        for impact in range(1, 6):
            cell_score = likelihood * impact
            n = counts[(likelihood, impact)]
            css = RATING_CLASS[rating_for(cell_score)]
            label = f"{n} risk{'s' if n != 1 else ''}, likelihood {likelihood}, impact {impact}"
            content = f"<b>{n}</b>" if n else f"<small>{cell_score}</small>"
            cells += f'<div class="giq-hm-cell {css} {"has" if n else ""}" title="{label}">{content}</div>'
    cells += "<div></div>" + "".join(f'<div class="giq-hm-axis">{i}</div>' for i in range(1, 6))
    st.html(
        f"""
        <div class="giq-hm-wrap">
          <div class="giq-hm-ylabel">Likelihood</div>
          <div>
            <div class="giq-hm" role="img" aria-label="Inherent risk heat map">{cells}</div>
            <div class="giq-hm-xlabel">Impact</div>
          </div>
          <div class="giq-hm-note">
            <h4>Reading the map</h4>
            <p>Each cell counts the risks with that likelihood and impact. Bold numbers are risks;
            faint numbers show the cell's score.</p>
            <p>Colours follow the rating bands: Critical 20&ndash;25, High 10&ndash;16,
            Medium 5&ndash;9, Low 1&ndash;4.</p>
            <p>This is the inherent view. The residual map appears once control tests exist
            (Phase 6), because residual risk can only drop for controls that passed testing.</p>
          </div>
        </div>
        """
    )

# ---------- Trace a risk ----------
with trace_tab:
    by_label = {f"{r.code}: {r.title}": r for r in risks}
    picked = by_label[st.selectbox("Risk", list(by_label), index=3)]
    picked_rating = rating_for(picked.inherent_score)

    nodes = f"""
      <div class="giq-node is-open">
        <div class="giq-dot"></div>
        <div><div class="giq-kind">Risk, owned by {escape(picked.owner.full_name)}</div>
          <div class="giq-title">{escape(picked.title)}</div>
          <div class="giq-id">{picked.code}, L{picked.likelihood} x I{picked.impact}</div></div>
        <span class="giq-chip {"fail" if picked_rating == "Critical" else "high"}">
          {picked_rating}, {picked.inherent_score}</span>
      </div>"""
    for control in picked.controls:
        refs = ", ".join(f"{FRAMEWORK_LABELS[req.framework.code]} {req.ref}" for req in control.requirements)
        nodes += f"""
      <div class="giq-node">
        <div class="giq-dot"></div>
        <div><div class="giq-kind">Control</div>
          <div class="giq-title">{escape(control.title)}</div>
          <div class="giq-id">{control.code} maps to {escape(refs)}</div></div>
        <span class="giq-chip plain">{"Key control" if control.is_key else control.nature}</span>
      </div>"""
    nodes += """
      <div class="giq-node is-pending">
        <div class="giq-dot"></div>
        <div><div class="giq-kind">Test and evidence</div>
          <div class="giq-title">Not tested yet</div>
          <div class="giq-id">Control testing and evidence arrive in Phase 6</div></div>
        <span class="giq-chip plain">Pending</span>
      </div>"""
    st.html(
        f'<div class="giq-trace giq-trace-wide"><div class="giq-trace-head"><h3>Audit trace</h3>'
        f"<span>Live record</span></div>{nodes}</div>"
    )

# ---------- Add a risk ----------
with add_tab:
    # Admins and auditors never own risks (see docs/roles-and-access.md).
    users = session.scalars(
        select(User).where(User.role.not_in(("Admin", "Auditor"))).order_by(User.full_name)
    ).all()
    controls = session.scalars(select(Control).order_by(Control.code)).all()
    st.markdown("Every new risk needs an owner, a score and a treatment. Mitigated risks need a control.")

    with st.form("add_risk", clear_on_submit=True, border=False):
        title = st.text_input(
            "Risk title", placeholder="e.g. Loan officers export customer lists to USB drives"
        )
        col1, col2, col3 = st.columns(3)
        category = col1.selectbox("Category", CATEGORIES)
        owner = col2.selectbox("Owner", users, format_func=lambda u: f"{u.full_name} ({u.department})")
        treatment = col3.selectbox("Treatment", TREATMENTS)
        col4, col5, col6 = st.columns(3)
        likelihood = col4.slider("Likelihood", 1, 5, 3, help="1 Rare to 5 Almost certain")
        impact = col5.slider("Impact", 1, 5, 3, help="1 Minimal to 5 Severe")
        due = col6.date_input("Treatment due", value=date.today() + timedelta(days=30))
        linked = st.multiselect(
            "Linked controls",
            controls,
            format_func=lambda c: f"{c.code}: {c.title}",
            placeholder="Choose controls",
        )
        submitted = st.form_submit_button("Add risk", type="primary")

    if submitted:
        new = NewRisk(
            title=title,
            category=category,
            owner_username=owner.username,
            likelihood=likelihood,
            impact=impact,
            treatment=treatment,
            due_date=due,
            control_codes=[c.code for c in linked],
        )
        try:
            saved = create_risk(session, new, actor=current_actor())
        except ValueError as problem:
            st.error(f"Risk not added. {problem}", icon=":material/error:")
        else:
            # Remember the message, then reload so the counts, table and heat map include the new risk.
            st.session_state["risk_added"] = (
                f"Added {saved.code}, rated {rating_for(saved.inherent_score)} ({saved.inherent_score}). "
                "The change is recorded in the audit log."
            )
            st.rerun()

    if "risk_added" in st.session_state:
        st.success(st.session_state.pop("risk_added"), icon=":material/check_circle:")

session.close()
