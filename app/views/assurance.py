"""Testing and findings: test controls with evidence, track findings to closure, re-rate residual risk."""

from datetime import date, timedelta
from html import escape

import pandas as pd
import streamlit as st
from sqlalchemy import select

from governiq.assurance import (
    METHODS,
    TESTER_ROLES,
    NewTest,
    add_action,
    complete_action,
    effective_controls,
    evidence_dir,
    latest_operating_results,
    load_findings,
    load_tests,
    record_test,
    rerate_residual,
    verify_evidence,
)
from governiq.automation import CHECKS, EXPORTS_TAKEN_ON, run_check
from governiq.controls import SAMPLE_SIZES
from governiq.models import Control, User
from governiq.risks import load_risks, rating_for
from governiq.ui import current_actor, get_session

RESULT_STYLE = {
    "Effective": "background-color:#DCEFEA;color:#17605A;font-weight:600",
    "Ineffective": "background-color:#F6DDE0;color:#8E2433;font-weight:600",
}
RATING_CLASS = {"Critical": "crit", "High": "high", "Medium": "med", "Low": "low"}

session = get_session()
actor = session.scalar(select(User).where(User.username == current_actor()))
tests = load_tests(session)
findings = load_findings(session)
latest = latest_operating_results(session)
working = effective_controls(session)
controls = session.scalars(select(Control).order_by(Control.code)).all()
open_findings = [f for f in findings if f.status == "Open"]

failed = sum(1 for t in tests if t.result == "Ineffective")
st.html(
    f"""
    <div class="giq-page-head">
      <h1>Testing and findings</h1>
      <p>{len(tests)} control tests recorded: {len(tests) - failed} effective, {failed} ineffective.
      {len(open_findings)} findings open. {len(working)} of {len(controls)} controls are proven effective
      by their latest operating test, so only risks treated by those controls can show lower
      residual risk.</p>
    </div>
    """
)

if "assurance_flash" in st.session_state:
    kind, message = st.session_state.pop("assurance_flash")
    (st.success if kind == "ok" else st.warning)(message, icon=":material/info:")

record_tab, auto_tab, log_tab, findings_tab, residual_tab = st.tabs(
    ["Record a test", "Automated checks", "Test log and evidence", "Findings and actions", "Residual risk"]
)

# ---------- Record a test ----------
with record_tab:
    if actor.role not in TESTER_ROLES:
        st.info(
            f"You are acting as {actor.full_name} ({actor.role}). Only a GRC Analyst or the AI Governance "
            "Lead can record tests. Switch user in the sidebar to try it, or submit anyway to see the rule.",
            icon=":material/lock:",
        )
    with st.form("record_test", clear_on_submit=True, border=False):
        control = st.selectbox(
            "Control tested",
            controls,
            format_func=lambda c: f"{c.code}: {c.title} (owner {c.owner.full_name})",
        )
        col1, col2, col3 = st.columns(3)
        test_type = col1.radio("Test type", ("Operating", "Design"), horizontal=True)
        method = col2.selectbox("Method", METHODS, index=1)
        period = col3.text_input("Period tested", value="2026-Q4")
        col4, col5, col6 = st.columns(3)
        sample_size = col4.number_input("Sample size", min_value=1, max_value=500, value=1, step=1)
        exceptions = col5.number_input("Exceptions found", min_value=0, max_value=500, value=0, step=1)
        performed_on = col6.date_input("Performed on", value=date.today(), max_value=date.today())
        reviewers = session.scalars(
            select(User).where(User.role.not_in(("Admin", "Auditor"))).order_by(User.full_name)
        ).all()
        reviewer = st.selectbox(
            "Reviewer",
            [None, *reviewers],
            format_func=lambda u: "No reviewer yet" if u is None else u.full_name,
        )
        notes = st.text_area("Notes", placeholder="What you sampled and what you found")
        files = st.file_uploader(
            "Evidence files (PDF, Excel, CSV, Word, text or images, up to 10 MB each)",
            accept_multiple_files=True,
            type=["pdf", "xlsx", "csv", "docx", "txt", "png", "jpg", "jpeg"],
        )
        st.caption(
            "Guide: sample sizes by frequency are "
            + ", ".join(f"{freq.lower()} {size.split(' ')[0]}" for freq, size in SAMPLE_SIZES.items())
            + ". The result is set from the exceptions: none means Effective."
        )
        submitted = st.form_submit_button("Record test", type="primary")

    if submitted:
        try:
            outcome = record_test(
                session,
                NewTest(
                    control_code=control.code,
                    test_type=test_type,
                    method=method,
                    period=period,
                    sample_size=int(sample_size),
                    exceptions=int(exceptions),
                    performed_on=performed_on,
                    reviewer_username=reviewer.username if reviewer else None,
                    notes=notes,
                ),
                actor=actor.username,
                evidence_files=[(f.name, f.getvalue()) for f in files or []],
            )
        except ValueError as problem:
            st.error(f"Test not recorded. {problem}", icon=":material/error:")
        else:
            message = f"Recorded {outcome.test.code}: {outcome.test.result}."
            if outcome.opened:
                message += f" Opened {outcome.opened.code} ({outcome.opened.severity})."
            for finding in outcome.closed:
                message += f" Closed {finding.code}: actions done and the retest passed."
            for finding in outcome.still_open:
                message += f" {finding.code} stays open until all its actions are done."
            st.session_state["assurance_flash"] = ("ok", message)
            st.rerun()

# ---------- Automated checks ----------
with auto_tab:
    st.markdown(
        f"Continuous control monitoring: each check reads a synthetic system export (taken "
        f"{EXPORTS_TAKEN_ON:%d %b %Y}), tests the **whole population** instead of a sample, and records the "
        "result as an operating test with the exception list attached as evidence. A failed check opens "
        "a finding; a passing re-run can close one."
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Check": c.code,
                    "What it looks for": c.name,
                    "Control": c.control_code,
                    "Data source": c.source,
                }
                for c in CHECKS
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    chosen = st.multiselect(
        "Checks to run",
        [c.code for c in CHECKS],
        default=[c.code for c in CHECKS],
        format_func=lambda code: f"{code} {next(c.name for c in CHECKS if c.code == code)}",
    )
    if st.button("Run checks", type="primary", icon=":material/play_arrow:", disabled=not chosen):
        results = []
        for code in chosen:
            try:
                result, outcome = run_check(session, code, actor=actor.username)
            except ValueError as problem:
                st.error(f"{code} not run. {problem}", icon=":material/error:")
                break
            note = f"{outcome.test.code} {outcome.test.result}"
            if outcome.opened:
                note += f", opened {outcome.opened.code}"
            note += "".join(f", closed {f.code}" for f in outcome.closed)
            note += "".join(f", {f.code} stays open (actions pending)" for f in outcome.still_open)
            results.append((code, result.population, result.exceptions, result.summary, note))
        else:
            st.session_state["ccm_results"] = results
            st.rerun()
    for code, population, exceptions, summary, note in st.session_state.get("ccm_results", []):
        icon = ":material/check_circle:" if not exceptions else ":material/warning:"
        with st.container(border=True):
            st.markdown(
                f"{icon} **{code}**: {population} checked, {len(exceptions)} "
                f"exception{'' if len(exceptions) == 1 else 's'}. {note}."
            )
            st.caption(summary)
            if exceptions:
                st.dataframe(pd.DataFrame(exceptions), hide_index=True, width="stretch")

# ---------- Test log and evidence ----------
with log_tab:
    log = pd.DataFrame(
        [
            {
                "Test": t.code,
                "Control": t.control.code,
                "Type": t.test_type,
                "Method": t.method,
                "Period": t.period,
                "Sample": t.sample_size,
                "Exceptions": t.exceptions,
                "Result": t.result,
                "Tester": t.tester.full_name,
                "Reviewer": t.reviewer.full_name if t.reviewer else "",
                "Evidence": len(t.evidence),
                "Date": t.performed_on,
            }
            for t in tests
        ]
    )
    st.dataframe(
        log.style.map(lambda r: RESULT_STYLE.get(r, ""), subset=["Result"]),
        hide_index=True,
        width="stretch",
        column_config={"Date": st.column_config.DateColumn(format="D MMM YYYY")},
    )
    by_code = {f"{t.code}: {t.control.title}": t for t in tests}
    chosen = by_code[st.selectbox("Open a test", list(by_code))]
    st.markdown(f"**Notes:** {chosen.notes or 'None'}")
    check = st.button("Verify evidence fingerprints", icon=":material/fingerprint:")
    for ev in chosen.evidence:
        left, right = st.columns([5, 2])
        status = ""
        if check:
            status = "Verified, unchanged" if verify_evidence(ev) else "MISMATCH, file changed or missing"
        left.html(
            f'<div class="giq-ev"><b>{escape(ev.code)}</b> {escape(ev.filename)}'
            f"<span>{ev.size_bytes:,} bytes, uploaded by {escape(ev.uploaded_by.full_name)}</span>"
            f"<code>sha256 {ev.sha256}</code>"
            + (
                f'<em class="{"ok" if status.startswith("Verified") else "bad"}">{status}</em>'
                if status
                else ""
            )
            + "</div>"
        )
        path = evidence_dir() / ev.stored_name
        if path.exists():
            right.download_button(
                "Download",
                path.read_bytes(),
                file_name=ev.filename,
                key=f"dl-{ev.code}",
                icon=":material/download:",
            )

# ---------- Findings and actions ----------
with findings_tab:
    if not findings:
        st.info("No findings yet. A failed test opens one automatically.")
    for finding in findings:
        done = sum(1 for a in finding.actions if a.status == "Done")
        state = "closed" if finding.status == "Closed" else "open"
        with st.container(border=True):
            st.html(
                f"""<div class="giq-fnd {state}">
                  <div><span class="giq-fnd-code">{finding.code}, from {finding.test.code},
                  raised {finding.raised_on:%d %b %Y}</span>
                  <h4>{escape(finding.title)}</h4>
                  <p>Control {finding.control.code}, owned by {escape(finding.control.owner.full_name)}.
                  Actions done: {done} of {len(finding.actions)}.</p></div>
                  <div class="giq-fnd-tags">
                    <span class="sev-{finding.severity.lower()}">{finding.severity}</span>
                    <span class="st-{state}">{finding.status}</span>
                  </div>
                </div>"""
            )
            for action in finding.actions:
                cols = st.columns([6, 2, 2])
                cols[0].markdown(
                    f"**{action.code}** {action.description}  \n"
                    f"Owner {action.owner.full_name}, due {action.due_date:%d %b %Y}"
                )
                cols[1].markdown("Done" if action.status == "Done" else "Open")
                if action.status == "Open" and cols[2].button("Mark done", key=f"done-{action.code}"):
                    try:
                        complete_action(session, action.code, actor.username)
                    except ValueError as problem:
                        st.session_state["assurance_flash"] = ("warn", str(problem))
                    else:
                        st.session_state["assurance_flash"] = (
                            "ok",
                            f"{action.code} done. {finding.code} closes when a new operating test of "
                            f"{finding.control.code} passes.",
                        )
                    st.rerun()
            if finding.status == "Open":
                with st.expander("Add a corrective action"):
                    with st.form(f"action-{finding.code}", clear_on_submit=True, border=False):
                        description = st.text_input("Action", key=f"desc-{finding.code}")
                        owner = st.selectbox(
                            "Owner", reviewers, format_func=lambda u: u.full_name, key=f"own-{finding.code}"
                        )
                        due = st.date_input(
                            "Due", value=date.today() + timedelta(days=30), key=f"due-{finding.code}"
                        )
                        if st.form_submit_button("Add action"):
                            try:
                                add_action(
                                    session, finding.code, description, owner.username, due, actor.username
                                )
                            except ValueError as problem:
                                st.session_state["assurance_flash"] = ("warn", str(problem))
                            else:
                                st.session_state["assurance_flash"] = (
                                    "ok",
                                    f"Action added to {finding.code}.",
                                )
                            st.rerun()
    st.caption(
        "A finding closes itself when every action is done and a later operating test of the same control "
        "passes. Nobody can close it by hand."
    )

# ---------- Residual risk ----------
with residual_tab:
    risks = load_risks(session)
    by_label = {f"{r.code}: {r.title}": r for r in risks}
    risk = by_label[st.selectbox("Risk", list(by_label))]
    chips = ""
    for c in risk.controls:
        test = latest.get(c.code)
        state = "ok" if c.code in working else ("bad" if test else "none")
        word = {"ok": "Effective", "bad": "Ineffective", "none": "Not tested"}[state]
        when = f", {test.code}" if test else ""
        chips += (
            f'<li class="{state}"><div><b>{c.code}</b> {escape(c.title)}</div><span>{word}{when}</span></li>'
        )
    can_reduce = any(c.code in working for c in risk.controls)
    st.html(
        f"""<div class="giq-res">
          <p>Inherent score <b>{risk.inherent_score}</b> ({rating_for(risk.inherent_score)}).
          {
            "At least one linked control is proven effective, so residual risk may be lower."
            if can_reduce
            else "No linked control is proven effective yet, so residual risk must stay at inherent."
        }</p>
          <ul>{chips}</ul></div>"""
    )
    col1, col2, col3 = st.columns([2, 2, 1])
    res_l = col1.slider("Residual likelihood", 1, 5, risk.residual_likelihood or risk.likelihood)
    res_i = col2.slider("Residual impact", 1, 5, risk.residual_impact or risk.impact)
    col3.metric(
        "Residual score", res_l * res_i, delta=res_l * res_i - risk.inherent_score, delta_color="inverse"
    )
    if st.button("Save residual rating", type="primary"):
        try:
            rerate_residual(session, risk.code, res_l, res_i, actor.username)
        except ValueError as problem:
            st.error(f"Not saved. {problem}", icon=":material/error:")
        else:
            st.session_state["assurance_flash"] = (
                "ok",
                f"{risk.code} residual set to {res_l * res_i} ({rating_for(res_l * res_i)}). Logged.",
            )
            st.rerun()

    rated = [r for r in risks if r.residual_likelihood]
    counts = {(likelihood, impact): 0 for likelihood in range(1, 6) for impact in range(1, 6)}
    for r in rated:
        counts[(r.residual_likelihood, r.residual_impact)] += 1
    cells = ""
    for likelihood in range(5, 0, -1):
        cells += f'<div class="giq-hm-axis">{likelihood}</div>'
        for impact in range(1, 6):
            n = counts[(likelihood, impact)]
            css = RATING_CLASS[rating_for(likelihood * impact)]
            cells += f'<div class="giq-hm-cell {css} {"has" if n else ""}">{f"<b>{n}</b>" if n else ""}</div>'
    cells += "<div></div>" + "".join(f'<div class="giq-hm-axis">{i}</div>' for i in range(1, 6))
    st.html(
        f"""<h4 class="giq-sub">Residual heat map: {len(rated)} of {len(risks)} risks re-rated so far</h4>
        <div class="giq-hm giq-hm-small" role="img" aria-label="Residual risk heat map">{cells}</div>"""
    )

session.close()
