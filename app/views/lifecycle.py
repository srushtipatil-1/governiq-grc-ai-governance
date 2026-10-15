"""AI lifecycle: stage gates with a go-live checklist, versioned model cards and post-launch reviews."""

from datetime import date
from html import escape

import pandas as pd
import streamlit as st
from sqlalchemy import select

from governiq.ai_governance import load_ai_systems
from governiq.lifecycle import (
    MODEL_CARD_FIELDS,
    NEXT_STAGE,
    PIR_OUTCOMES,
    REVIEW_EVERY_DAYS,
    STAGES,
    advance_stage,
    card_for,
    gate_checklist,
    load_gates,
    missing_card_fields,
    model_card_markdown,
    next_review_due,
    record_review,
    retire_system,
    review_status,
    reviews_for,
    save_model_card,
)
from governiq.models import User
from governiq.ui import current_actor, get_session

BAND = {"High risk": "crit", "Prohibited": "crit", "Limited risk": "high", "Minimal risk": "low"}
STATUS_ICON = {
    "Overdue": ":material/error:",
    "Due soon": ":material/schedule:",
    "On track": ":material/check_circle:",
}

session = get_session()
actor = session.scalar(select(User).where(User.username == current_actor()))
systems = load_ai_systems(session)
today = date.today()
live = [s for s in systems if s.lifecycle_stage == "Deployed"]
due = {s.code: next_review_due(s, reviews_for(session, s)) for s in live}
overdue = [s for s in live if review_status(due[s.code], today) == "Overdue"]
blocked = [s for s in systems if any(not item.ok for item in gate_checklist(session, s))]

st.html(
    f"""
    <div class="giq-page-head">
      <h1>AI lifecycle</h1>
      <p>{len(live)} AI systems live, {len(systems) - len(live)} in the pipeline. {len(blocked)} cannot
      move to their next stage until their gate checks pass. {len(overdue)} post-implementation review
      {"is" if len(overdue) == 1 else "are"} overdue. Every gate decision is stored with the checklist as it
      stood on the day.</p>
    </div>
    """
)

if "life_flash" in st.session_state:
    kind, message = st.session_state.pop("life_flash")
    (st.success if kind == "ok" else st.warning)(message, icon=":material/info:")

gates_tab, cards_tab, reviews_tab = st.tabs(["Stage gates", "Model cards", "Post-launch reviews"])

# ---------- Stage gates ----------
with gates_tab:
    columns = ""
    for stage in (*STAGES, "Retired"):
        cards = "".join(
            f'<div class="giq-pipe-card {BAND.get(s.external_tier, "low")}"><b>{escape(s.name)}</b>'
            f"<span>{s.code}, {escape(s.external_tier or '')}, tier {s.internal_tier}</span></div>"
            for s in systems
            if s.lifecycle_stage == stage
        )
        cards = cards or '<div class="giq-pipe-empty">None</div>'
        columns += f'<div class="giq-pipe-col"><h5>{stage}</h5>{cards}</div>'
    st.html(f'<div class="giq-pipe">{columns}</div>')

    pipeline = [s for s in systems if s.lifecycle_stage in NEXT_STAGE] or systems
    system = st.selectbox(
        "AI system",
        pipeline,
        format_func=lambda s: f"{s.code} {s.name} ({s.lifecycle_stage}, owner {s.owner.full_name})",
    )
    target = NEXT_STAGE.get(system.lifecycle_stage)
    if target:
        checklist = gate_checklist(session, system)
        rows = (
            "".join(
                f'<li class="{"ok" if item.ok else "bad"}"><div><b>{"PASS" if item.ok else "FAIL"}</b>'
                f"{escape(item.label)}</div><span>{escape(item.detail)}</span></li>"
                for item in checklist
            )
            or '<li class="none"><div>No checks for this gate.</div><span>Open</span></li>'
        )
        st.html(
            f'<div class="giq-sub">Gate: {system.lifecycle_stage} to {target}</div>'
            f'<div class="giq-res"><ul>{rows}</ul></div>'
        )
        note = st.text_input("Decision note (optional)", key=f"gate-note-{system.code}")
        if st.button(f"Move {system.name} to {target}", type="primary", icon=":material/arrow_forward:"):
            try:
                advance_stage(session, system.code, actor.username, note)
            except ValueError as problem:
                st.error(str(problem), icon=":material/block:")
            else:
                st.session_state["life_flash"] = ("ok", f"{system.name} moved to {target}.")
                st.rerun()
    else:
        st.info(f"{system.name} is {system.lifecycle_stage}; there is no next stage.", icon=":material/info:")
    if system.lifecycle_stage != "Retired":
        with st.expander(f"Retire {system.name}"):
            reason = st.text_input("Reason", key=f"retire-{system.code}")
            if st.button("Retire system", key=f"retire-btn-{system.code}"):
                try:
                    retire_system(session, system.code, actor.username, reason)
                except ValueError as problem:
                    st.error(str(problem), icon=":material/block:")
                else:
                    st.session_state["life_flash"] = ("ok", f"{system.name} retired.")
                    st.rerun()

    gates = load_gates(session)
    if gates:
        st.html('<div class="giq-sub">Gate decisions</div>')
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Date": g.decided_on,
                        "System": g.ai_system.name,
                        "From": g.from_stage,
                        "To": g.to_stage,
                        "Decided by": g.decided_by.full_name,
                        "Note": g.note,
                    }
                    for g in gates
                ]
            ),
            hide_index=True,
            width="stretch",
        )

# ---------- Model cards ----------
with cards_tab:
    system = st.selectbox(
        "AI system",
        systems,
        key="card-system",
        format_func=lambda s: f"{s.code} {s.name} (owner {s.owner.full_name})",
    )
    card = card_for(session, system)
    missing = missing_card_fields(system, card)
    if card:
        st.caption(
            f"Version {card.version}, updated {card.updated_on:%d %b %Y} by {card.updated_by.full_name}."
        )
    if missing:
        st.warning("Incomplete. Still needed: " + ", ".join(missing) + ".", icon=":material/edit_note:")
    else:
        st.success("Complete: every required section is written.", icon=":material/task_alt:")
    with st.form(f"card-{system.code}", border=False):
        values = {}
        for field, label, guidance in MODEL_CARD_FIELDS:
            if field == "transparency_notice" and not system.interacts_with_people:
                continue
            values[field] = st.text_area(
                label, value=getattr(card, field) if card else "", placeholder=guidance, height=90
            )
        save = st.form_submit_button("Save new version", type="primary")
    if save:
        try:
            saved = save_model_card(session, system.code, values, actor.username)
        except ValueError as problem:
            st.error(str(problem), icon=":material/error:")
        else:
            st.session_state["life_flash"] = (
                "ok",
                f"Saved {system.name} model card, version {saved.version}.",
            )
            st.rerun()
    if card:
        st.download_button(
            "Download model card (Markdown)",
            model_card_markdown(system, card),
            file_name=f"{system.code}-{system.name}-model-card.md",
            mime="text/markdown",
            icon=":material/download:",
        )

# ---------- Post-launch reviews ----------
with reviews_tab:
    st.markdown(
        "Live systems are reviewed on a cycle set by their internal tier: "
        + ", ".join(f"tier {tier} every {days} days" for tier, days in REVIEW_EVERY_DAYS.items())
        + ". A review checks the system still performs, stays fair, and is used as approved."
    )
    for s in live:
        reviews = reviews_for(session, s)
        status = review_status(due[s.code], today)
        last = reviews[0] if reviews else None
        with st.container(border=True):
            st.markdown(
                f"{STATUS_ICON[status]} **{s.name}**: {status.lower()}, "
                f"next review due {due[s.code]:%d %b %Y}. "
                f"Live since {s.deployed_on:%d %b %Y}. "
                + (
                    f"Last review {last.code} on {last.reviewed_on:%d %b %Y}: {last.outcome}."
                    if last
                    else "Never reviewed."
                )
            )
            if last:
                st.caption(last.notes)
    if live:
        with st.form("pir", border=False):
            st.html('<div class="giq-sub">Record a review</div>')
            target = st.selectbox("Live AI system", live, format_func=lambda s: f"{s.code} {s.name}")
            outcome = st.radio("Outcome", PIR_OUTCOMES, horizontal=True)
            notes = st.text_area(
                "What was checked and found", placeholder="Accuracy, drift, fairness, complaints, overrides"
            )
            submit = st.form_submit_button("Record review", type="primary")
        if submit:
            try:
                review = record_review(session, target.code, outcome, notes, actor.username)
            except ValueError as problem:
                st.error(str(problem), icon=":material/error:")
            else:
                st.session_state["life_flash"] = (
                    "ok",
                    f"Recorded {review.code} for {target.name}: {outcome}.",
                )
                st.rerun()
