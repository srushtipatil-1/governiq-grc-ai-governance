"""Dashboard: headline numbers, key risk indicators, the committee pack and the audit evidence pack."""

from datetime import date
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

from governiq.reporting import (
    RAG_ORDER,
    _decisions,
    _summary_lines,
    audit_pack_zip,
    committee_pack_pdf,
    compute_kris,
    headline,
    rag_counts,
)
from governiq.ui import get_session

session = get_session()
today = date.today()
kris = compute_kris(session, today)
head = headline(session, today)
rags = rag_counts(kris)

st.html(
    f"""
    <div class="giq-page-head">
      <h1>Dashboard</h1>
      <p>Kshitij Finserv's cyber, privacy and AI risk position on one page, computed live from the register,
      control tests, findings and AI records. {rags["Red"]} key risk indicators are red, {rags["Amber"]} amber
      and {rags["Green"]} green.</p>
    </div>
    """
)

overview_tab, kri_tab, committee_tab, audit_tab = st.tabs(
    ["Overview", "Key risk indicators", "Committee pack", "Audit pack"]
)


def tile(label: str, value: str, note: str, tone: str) -> str:
    return (
        f'<div class="giq-tile {tone}"><span>{escape(label)}</span><b>{escape(value)}</b>'
        f"<small>{escape(note)}</small></div>"
    )


# ---------- Overview ----------
with overview_tab:
    crit_high = head["inherent"]["Critical"] + head["inherent"]["High"]
    res_crit_high = head["residual"]["Critical"] + head["residual"]["High"]
    st.html(
        '<div class="giq-tiles">'
        + tile(
            "Critical and high risks",
            f"{res_crit_high}",
            f"{crit_high} before controls, of {head['risks']} risks",
            "warn" if res_crit_high else "ok",
        )
        + tile(
            "Controls proven effective",
            f"{head['controls_effective']}/{head['controls']}",
            f"{head['controls_tested']} have an operating test",
            "mid",
        )
        + tile(
            "Open findings",
            str(head["open_findings"]),
            f"{head['findings_by_severity']['High']} high severity",
            "warn" if head["open_findings"] else "ok",
        )
        + tile(
            "AI systems",
            str(head["ai_systems"]),
            f"{head['ai_live']} live, {head['ai_tiers'].get('High risk', 0)} high risk",
            "mid",
        )
        + "</div>"
    )
    left, right = st.columns([1.1, 1])
    with left:
        st.html('<div class="giq-sub">Risks by rating, before and after proven controls</div>')
        ratings = ["Critical", "High", "Medium", "Low"]
        frame = pd.DataFrame(
            [{"Rating": r, "View": view, "Risks": head[key][r]}
             for r in ratings for view, key in (("Inherent", "inherent"), ("Residual", "residual"))]
        )  # fmt: skip
        chart = (
            alt.Chart(frame)
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("Rating:N", sort=ratings, title=None, axis=alt.Axis(labelAngle=0)),
                xOffset=alt.XOffset("View:N", sort=["Inherent", "Residual"]),
                y=alt.Y("Risks:Q", title="Risks"),
                color=alt.Color(
                    "View:N",
                    scale=alt.Scale(domain=["Inherent", "Residual"], range=["#14213D", "#E8A33D"]),
                    legend=alt.Legend(orient="bottom", title=None),
                ),
                tooltip=["Rating", "View", "Risks"],
            )
            .properties(height=280)
        )
        st.altair_chart(chart, width="stretch")
    with right:
        st.html('<div class="giq-sub">Needs attention</div>')
        urgent = [k for k in sorted(kris, key=lambda k: (RAG_ORDER[k.rag], k.code)) if k.rag != "Green"]
        rows = "".join(
            f"<li><code>{k.code}</code><div>{escape(k.name)}<small>{escape(k.owner)}</small></div>"
            f'<div class="val">{escape(k.display)}</div><div class="rag {k.rag}">{k.rag}</div></li>'
            for k in urgent[:6]
        )
        st.html(f'<ul class="giq-kri compact">{rows}</ul>')

# ---------- Key risk indicators ----------
with kri_tab:
    st.markdown(
        "Each indicator has an owner and amber and red thresholds set by the risk appetite. Zero-tolerance "
        "indicators, such as a leaver with live access, go straight to red."
    )
    rows = "".join(
        f"<li><code>{k.code}</code><div>{escape(k.name)}<small>{escape(k.area)} &middot; {escape(k.owner)} "
        f"&middot; {escape(k.threshold)}<br>{escape(k.note)}</small></div>"
        f'<div class="val">{escape(k.display)}</div><div class="rag {k.rag}">{k.rag}</div></li>'
        for k in sorted(kris, key=lambda k: (RAG_ORDER[k.rag], k.code))
    )
    st.html(f'<ul class="giq-kri">{rows}</ul>')

# ---------- Committee pack ----------
with committee_tab:
    st.markdown("A two-page PDF for the Risk & AI Governance Committee, generated from today's data.")
    with st.container(border=True):
        st.markdown("**Executive summary**")
        st.markdown("\n".join(f"- {line}" for line in _summary_lines(session, kris, head)))
        st.markdown("**Decisions requested**")
        st.markdown("\n".join(f"{i}. {ask}" for i, ask in enumerate(_decisions(kris), start=1)))
    st.download_button(
        "Download committee pack (PDF)",
        committee_pack_pdf(session, today),
        file_name=f"governiq-committee-pack-{today:%Y-%m}.pdf",
        mime="application/pdf",
        type="primary",
        icon=":material/picture_as_pdf:",
    )

# ---------- Audit pack ----------
with audit_tab:
    data, manifest = audit_pack_zip(session, today)
    st.markdown(
        "Everything an internal or external auditor typically requests, in one ZIP: register, risk and "
        "control matrix, test log, findings, every evidence file, AI records, KRIs and the verified audit "
        "trail. **MANIFEST.csv** lists the SHA-256 hash of every file so the pack can be checked after "
        "hand-over."
    )
    st.dataframe(
        pd.DataFrame(manifest).assign(sha256=lambda d: d.sha256.str[:16] + "..."),
        hide_index=True,
        width="stretch",
    )
    st.download_button(
        f"Download audit pack (ZIP, {len(manifest)} files)",
        data,
        file_name=f"governiq-audit-pack-{today:%Y-%m-%d}.zip",
        mime="application/zip",
        type="primary",
        icon=":material/folder_zip:",
    )
