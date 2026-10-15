"""Controls and framework mapping: one control library, tested once, counted across every framework."""

from datetime import date
from html import escape

import pandas as pd
import streamlit as st

from governiq.config import FRAMEWORK_LABELS
from governiq.controls import (
    control_rows,
    crosswalk,
    framework_coverage,
    frameworks_of,
    load_controls,
    rcm_rows,
    rcm_workbook,
    risks_by_control,
)
from governiq.ui import get_session

session = get_session()
controls = load_controls(session)
linked = risks_by_control(session)
coverage = framework_coverage(session)
total_reqs = sum(c.total for c in coverage)
mapped_reqs = sum(c.mapped for c in coverage)
multi = sum(1 for c in controls if len(frameworks_of(c)) > 1)

st.html(
    f"""
    <div class="giq-page-head">
      <h1>Controls and framework mapping</h1>
      <p>{len(controls)} internal controls cover {mapped_reqs} of {total_reqs} requirements across
      {len(coverage)} frameworks. {multi} controls satisfy more than one framework, so each is tested once
      and counted everywhere it applies.</p>
    </div>
    """
)

library_tab, coverage_tab, crosswalk_tab, rcm_tab = st.tabs(
    ["Control library", "Framework coverage", "Crosswalk", "Risk & control matrix"]
)

# ---------- Control library ----------
with library_tab:
    table = pd.DataFrame(control_rows(controls, linked))
    left, middle, right = st.columns([2, 2, 3])
    domains = left.multiselect("Domain", sorted(table["Domain"].unique()), placeholder="All domains")
    frameworks = middle.multiselect(
        "Framework", list(FRAMEWORK_LABELS.values()), placeholder="All frameworks"
    )
    key_only = right.toggle("Key controls only")

    view = table
    if domains:
        view = view[view["Domain"].isin(domains)]
    if frameworks:
        view = view[view["Frameworks"].apply(lambda listed: any(f in listed.split(", ") for f in frameworks))]
    if key_only:
        view = view[view["Key"] == "Yes"]

    st.caption(f"Showing {len(view)} of {len(table)} controls.")
    st.dataframe(
        view,
        hide_index=True,
        width="stretch",
        column_config={
            "Control": st.column_config.TextColumn(width="large"),
            "Frameworks": st.column_config.TextColumn(width="medium"),
            "Requirements": st.column_config.NumberColumn(help="Framework requirements this control maps to"),
            "Risks": st.column_config.NumberColumn(help="Risks in the register this control treats"),
        },
    )

    by_label = {f"{c.code}: {c.title}": c for c in controls}
    picked = by_label[st.selectbox("Inspect a control", list(by_label), index=4)]
    groups: dict[str, list[str]] = {}
    for req in picked.requirements:
        groups.setdefault(FRAMEWORK_LABELS[req.framework.code], []).append(
            f"<li><b>{escape(req.ref)}</b> {escape(req.title)}</li>"
        )
    columns = "".join(
        f'<div class="giq-map-col"><h5>{escape(name)}</h5><ul>{"".join(items)}</ul></div>'
        for name, items in groups.items()
    )
    risk_items = (
        "".join(f"<li><b>{r.code}</b> {escape(r.title)}</li>" for r in linked.get(picked.code, []))
        or "<li>No risk in the register uses this control yet.</li>"
    )
    st.html(
        f"""
        <div class="giq-map">
          <div class="giq-map-head">
            <div><span class="giq-map-code">{picked.code}</span><h4>{escape(picked.title)}</h4>
            <p>{picked.control_type}, {picked.nature.lower()}, {picked.frequency.lower()}.
            Owned by {escape(picked.owner.full_name)}.</p></div>
            <span class="giq-map-count">{len(groups)} framework{"s" if len(groups) != 1 else ""}</span>
          </div>
          <div class="giq-map-cols">{columns}</div>
          <div class="giq-map-risks"><h5>Treats these risks</h5><ul>{risk_items}</ul></div>
        </div>
        """
    )

# ---------- Framework coverage ----------
with coverage_tab:
    rows = ""
    for cov in coverage:
        gap_text = ", ".join(escape(g.ref) for g in cov.gaps) if cov.gaps else "No gaps"
        rows += f"""
        <div class="giq-cov-row">
          <div class="giq-cov-name"><b>{escape(cov.label)}</b><span>{escape(cov.claim_level)}</span></div>
          <div class="giq-cov-bar" role="img" aria-label="{cov.label} {cov.percent} percent mapped">
            <div style="width:{cov.percent}%"></div></div>
          <div class="giq-cov-num"><b>{cov.mapped}/{cov.total}</b> {cov.percent}%</div>
          <div class="giq-cov-gaps {"none" if not cov.gaps else ""}">{gap_text}</div>
        </div>"""
    st.html(
        f"""
        <div class="giq-cov">
          <div class="giq-cov-row giq-cov-head">
            <div>Framework</div><div>Requirements with a mapped control</div>
            <div>Mapped</div><div>Unmapped requirements (gaps)</div>
          </div>
          {rows}
        </div>
        <p class="giq-cov-note">Coverage shows design only: a requirement counts as covered when at least one
        control maps to it. Whether those controls work is measured by control testing in Phase 6.</p>
        """
    )
    gap_rows = [
        {"Framework": cov.label, "Requirement": g.ref, "What it asks for": g.title}
        for cov in coverage
        for g in cov.gaps
    ]
    st.markdown(f"**Gap register: {len(gap_rows)} requirements with no control yet**")
    st.dataframe(pd.DataFrame(gap_rows), hide_index=True, width="stretch")


# ---------- Crosswalk ----------
def _shade(count: int) -> str:
    """Darker teal = more requirements covered."""
    if count >= 4:
        return "background-color:#1F7A6E;color:#FFFFFF;font-weight:600"
    if count >= 2:
        return "background-color:#7FBFB4;color:#0E3B36;font-weight:600"
    if count == 1:
        return "background-color:#DCEFEA;color:#17605A"
    return "color:#B5BFCC"


with crosswalk_tab:
    grid = pd.DataFrame(crosswalk(controls)).T.sort_index(key=lambda names: names.str.lower())
    st.markdown(
        "Requirements covered by each control domain, per framework. Darker cells carry more coverage."
    )
    st.dataframe(grid.style.map(_shade), width="stretch", height=36 * (len(grid) + 1) + 3)

# ---------- Risk & control matrix ----------
with rcm_tab:
    rcm = pd.DataFrame(rcm_rows(session))
    st.markdown(
        f"The Risk & Control Matrix lists every risk-control pair ({len(rcm)} rows) with test steps and "
        "sample sizes, in the layout audit teams use to plan control testing."
    )
    st.download_button(
        "Download RCM as Excel",
        rcm_workbook(session),
        file_name=f"governiq-rcm-{date.today().isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/download:",
        type="primary",
    )
    st.dataframe(
        rcm[["Risk ID", "Control ID", "Control", "Key control", "Frequency", "Sample size", "Test result"]],
        hide_index=True,
        width="stretch",
    )

session.close()
