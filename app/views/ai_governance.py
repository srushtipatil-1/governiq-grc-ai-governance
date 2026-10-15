"""AI governance: inventory, purpose-based risk tiering, NIST AI RMF assessment and independent approval."""

import json
from html import escape

import pandas as pd
import streamlit as st
from sqlalchemy import select

from governiq.ai_governance import (
    ANSWERS,
    ASSESSOR_ROLES,
    AUTONOMY_LEVELS,
    BUILD_TYPES,
    DOMAINS,
    FUNCTIONS,
    QUESTIONS,
    NewAISystem,
    decide_assessment,
    function_scores,
    latest_assessment,
    load_ai_systems,
    load_assessments,
    register_ai_system,
    submit_assessment,
)
from governiq.models import User, Vendor
from governiq.ui import current_actor, get_session

TIER_CLASS = {"Prohibited": "sev-high", "High risk": "sev-high", "Limited risk": "sev-medium"}
STATUS_CLASS = {"Approved": "st-closed", "Submitted": "st-open", "Rejected": "sev-high"}

session = get_session()
actor = session.scalar(select(User).where(User.username == current_actor()))
systems = load_ai_systems(session)
assessments = load_assessments(session)
pending = [a for a in assessments if a.status == "Submitted"]
high = sum(1 for s in systems if s.external_tier == "High risk")
unassessed = [s for s in systems if latest_assessment(assessments, s) is None]

st.html(
    f"""
    <div class="giq-page-head">
      <h1>AI governance</h1>
      <p>{len(systems)} AI systems in the inventory, {high} classified high risk by purpose.
      {len(unassessed)} not yet assessed, {len(pending)} assessments waiting for approval.
      Every tier shows the rule that produced it; every assessment is approved by someone other than
      the assessor and the system owner.</p>
    </div>
    """
)

if "ai_flash" in st.session_state:
    kind, message = st.session_state.pop("ai_flash")
    (st.success if kind == "ok" else st.warning)(message, icon=":material/info:")

inventory_tab, register_tab, assess_tab, approve_tab = st.tabs(
    ["AI inventory", "Register an AI use case", "Risk assessment", "Approvals"]
)


def scores_html(answers: dict[str, str]) -> str:
    rows = "".join(
        f'<li class="{"ok" if pct >= 80 else "bad"}"><div><b>{fn.upper()}</b>NIST AI RMF function</div>'
        f"<span>{pct}%</span></li>"
        for fn, pct in function_scores(answers).items()
    )
    return f'<div class="giq-res"><ul>{rows}</ul></div>'


# ---------- AI inventory ----------
with inventory_tab:
    for system in systems:
        last = latest_assessment(assessments, system)
        status = last.status if last else "Not assessed"
        tier_class = TIER_CLASS.get(system.external_tier, "sev-low")
        with st.container(border=True):
            st.html(
                f"""<div class="giq-fnd">
                  <div><span class="giq-fnd-code">{system.code}, {escape(system.build_type)},
                  {escape(system.lifecycle_stage)}, owner {escape(system.owner.full_name)}</span>
                  <h4>{escape(system.name)}</h4>
                  <p>{escape(system.purpose)}. {system.people_affected:,} people affected,
                  {escape(system.autonomy.lower())}.</p></div>
                  <div class="giq-fnd-tags">
                    <span class="{tier_class}">{system.external_tier}</span>
                    <span class="st-open">Tier {system.internal_tier}</span>
                    <span class="{STATUS_CLASS.get(status, "sev-medium")}">{status}</span>
                  </div>
                </div>"""
            )
            with st.expander("Why this tier, and the latest assessment"):
                st.markdown("\n".join(f"- {line}" for line in system.tier_reasons.splitlines()))
                if last:
                    st.caption(
                        f"{last.code} by {last.assessor.full_name} on {last.submitted_on:%d %b %Y}, "
                        f"{last.status.lower()}" + (f" by {last.approver.full_name}" if last.approver else "")
                    )
                    st.html(scores_html(json.loads(last.answers_json)))
    st.caption(
        "External tiers follow EU AI Act-style purpose rules as a reference method, not legal advice. "
        "Internal tier 1 means the strictest oversight: assessment before go-live and yearly review."
    )

# ---------- Register an AI use case ----------
with register_tab:
    if actor.role not in ASSESSOR_ROLES:
        st.info(
            f"You are acting as {actor.full_name} ({actor.role}). Only a GRC Analyst or the AI Governance "
            "Lead can register AI systems. Switch user in the sidebar, or submit anyway to see the rule.",
            icon=":material/lock:",
        )
    owners = session.scalars(
        select(User).where(User.role.not_in(("Admin", "Auditor"))).order_by(User.full_name)
    ).all()
    vendors = session.scalars(select(Vendor).order_by(Vendor.code)).all()
    with st.form("register_ai", border=False):
        col1, col2 = st.columns(2)
        name = col1.text_input("Name", placeholder="e.g. CollectWise")
        domain = col2.selectbox("What decisions does it support?", DOMAINS)
        purpose = st.text_input("Purpose", placeholder="e.g. Predicts which borrowers will miss an EMI")
        col3, col4, col5 = st.columns(3)
        model_type = col3.text_input("Model type", placeholder="e.g. Logistic regression")
        build_type = col4.selectbox("Built or bought", BUILD_TYPES)
        vendor = col5.selectbox(
            "Vendor (if bought or API)",
            [None, *vendors],
            format_func=lambda v: "None" if v is None else v.name,
        )
        col6, col7, col8 = st.columns(3)
        owner = col6.selectbox(
            "Business owner", owners, format_func=lambda u: f"{u.full_name}, {u.department}"
        )
        people = col7.number_input("People affected", min_value=0, value=1000, step=1000)
        autonomy = col8.selectbox("Human oversight", AUTONOMY_LEVELS)
        col9, col10, col11 = st.columns(3)
        personal = col9.checkbox("Uses personal data", value=True)
        decides = col10.checkbox("Decides about individuals")
        talks = col11.checkbox("Talks to people directly")
        register = st.form_submit_button("Register and classify", type="primary")
    if register:
        try:
            system = register_ai_system(
                session,
                NewAISystem(
                    name=name,
                    purpose=purpose,
                    domain=domain,
                    model_type=model_type,
                    build_type=build_type,
                    owner_username=owner.username,
                    vendor_code=vendor.code if vendor else None,
                    uses_personal_data=personal,
                    people_affected=int(people),
                    decides_on_individuals=decides,
                    interacts_with_people=talks,
                    autonomy=autonomy,
                ),
                actor=actor.username,
            )
        except ValueError as problem:
            st.error(str(problem), icon=":material/error:")
        else:
            st.session_state["ai_flash"] = (
                "ok",
                f"Registered {system.code} {system.name}: {system.external_tier}, internal tier "
                f"{system.internal_tier}. Next step: a risk assessment.",
            )
            st.rerun()

# ---------- Risk assessment ----------
with assess_tab:
    st.markdown(
        "Sixteen questions across the four NIST AI RMF functions. Each **No** or **Partial** on an important "
        "question becomes an AI risk in the register, linked to the control that would fix it."
    )
    target = st.selectbox(
        "AI system",
        systems,
        index=systems.index(unassessed[0]) if unassessed else 0,
        format_func=lambda s: f"{s.code} {s.name} ({s.external_tier}, owner {s.owner.full_name})",
    )
    with st.form("assess_ai", border=False):
        answers = {}
        for function in FUNCTIONS:
            st.html(f'<div class="giq-sub">{function}</div>')
            for q in (q for q in QUESTIONS if q.function == function):
                options = ANSWERS if q.allow_na else ANSWERS[:3]
                answers[q.id] = st.radio(
                    f"{q.id}. {q.text}",
                    options,
                    index=None,
                    horizontal=True,
                    key=f"q-{target.code}-{q.id}",
                    help=f"{q.characteristic}. Control {q.control}." + ("" if q.important else " Advisory."),
                )
        assess = st.form_submit_button("Submit for approval", type="primary")
    if assess:
        try:
            outcome = submit_assessment(
                session, target.code, {k: v for k, v in answers.items() if v}, actor=actor.username
            )
        except ValueError as problem:
            st.error(f"Not submitted. {problem}", icon=":material/error:")
        else:
            message = f"Submitted {outcome.assessment.code} for {target.name}."
            if outcome.risks_created:
                message += " New AI risks: " + ", ".join(r.code for r in outcome.risks_created) + "."
            st.session_state["ai_flash"] = ("ok", message)
            st.rerun()

# ---------- Approvals ----------
with approve_tab:
    if not pending:
        st.info("Nothing waiting for approval.", icon=":material/task_alt:")
    for a in pending:
        with st.container(border=True):
            st.markdown(
                f"**{a.code}** {a.ai_system.name} ({a.ai_system.external_tier}), assessed by "
                f"{a.assessor.full_name} on {a.submitted_on:%d %b %Y}"
            )
            st.html(scores_html(json.loads(a.answers_json)))
            note = st.text_input("Decision note", key=f"note-{a.code}")
            col1, col2, _ = st.columns([1, 1, 4])
            for col, label, approve in ((col1, "Approve", True), (col2, "Reject", False)):
                if col.button(label, key=f"{label}-{a.code}", type="primary" if approve else "secondary"):
                    try:
                        decide_assessment(session, a.code, approve, note, actor=actor.username)
                    except ValueError as problem:
                        st.session_state["ai_flash"] = ("warn", str(problem))
                    else:
                        st.session_state["ai_flash"] = (
                            "ok",
                            f"{a.code} {'approved' if approve else 'rejected'}.",
                        )
                    st.rerun()
    st.html('<div class="giq-sub">History</div>')
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Assessment": a.code,
                    "System": a.ai_system.name,
                    "Assessor": a.assessor.full_name,
                    "Status": a.status,
                    "Approver": a.approver.full_name if a.approver else "",
                    "Note": a.decision_note,
                }
                for a in assessments
            ]
        ),
        hide_index=True,
        width="stretch",
    )
