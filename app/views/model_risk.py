"""Model risk: independent validation of performance, fairness and drift, recorded as control tests."""

import json
from html import escape

import pandas as pd
import streamlit as st
from sqlalchemy import select

from governiq.model_risk import (
    FOUR_FIFTHS,
    MIN_FAIRNESS_RATIO,
    MODEL_DATA,
    PSI_ACT,
    PSI_WATCH,
    evaluate,
    load_validations,
    psi_band,
    record_validation,
)
from governiq.models import AISystem, User
from governiq.ui import current_actor, get_session

session = get_session()
actor = session.scalar(select(User).where(User.username == current_actor()))
systems = session.scalars(select(AISystem).where(AISystem.code.in_(MODEL_DATA)).order_by(AISystem.code)).all()
validations = load_validations(session)

system = systems[0]
if len(systems) > 1:
    system = st.selectbox("Model", systems, format_func=lambda s: f"{s.code} {s.name}")
spec = MODEL_DATA[system.code]
evaluation = evaluate(system.code)
failed = [c for c in evaluation.checks if not c.ok]

st.html(
    f"""
    <div class="giq-page-head">
      <h1>Model risk</h1>
      <p>Independent validation of {escape(system.name)} on {evaluation.sample:,} synthetic hold-out
      applications, plus a drift check against {escape(spec.production_label)} production scores.
      {len(evaluation.checks) - len(failed)} of {len(evaluation.checks)} checks pass.
      {"Failing: " + escape(", ".join(c.name for c in failed)) + "." if failed else ""}
      Recording a run turns each area into a control test, so a failure opens a finding.</p>
    </div>
    """
)

if "mr_flash" in st.session_state:
    kind, message = st.session_state.pop("mr_flash")
    (st.success if kind == "ok" else st.warning)(message, icon=":material/info:")

validation_tab, fairness_tab, drift_tab, history_tab = st.tabs(["Validation", "Fairness", "Drift", "History"])


def check_list(checks) -> str:
    rows = "".join(
        f'<li class="{"ok" if c.ok else "bad"}"><div><b>{"PASS" if c.ok else "FAIL"}</b>{escape(c.name)}: '
        f"{c.value:.3f} (limit {escape(c.limit)})<br><small>{escape(c.detail)}</small></div>"
        f"<span>{c.area}</span></li>"
        for c in checks
    )
    return f'<div class="giq-res"><ul>{rows}</ul></div>'


# ---------- Validation ----------
with validation_tab:
    st.html(check_list(evaluation.checks))
    st.caption(
        f"Approval threshold {spec.threshold}. Performance results feed CTL-AI-04, fairness CTL-AI-05 and "
        "drift CTL-AI-06. The validator must not own the model or those controls."
    )
    if st.button("Record validation run", type="primary", icon=":material/verified:"):
        try:
            run = record_validation(session, system.code, actor.username)
        except ValueError as problem:
            st.error(f"Not recorded. {problem}", icon=":material/block:")
        else:
            st.session_state["mr_flash"] = (
                "ok",
                f"Recorded {run.code}: {run.result}. Control tests {run.test_codes}. "
                "Failed areas open or keep open a finding on the Testing page.",
            )
            st.rerun()

# ---------- Fairness ----------
with fairness_tab:
    st.markdown(
        f"Approval rates are compared across groups. The **ratio** of the lowest to the highest rate must be "
        f"at least **{MIN_FAIRNESS_RATIO:.2f}** (Kshitij Finserv's appetite; the four-fifths rule floor is "
        f"{FOUR_FIFTHS:.2f}). The **equal opportunity gap** compares approval among people who did repay."
    )
    for attr, stats in evaluation.group_rates.items():
        top = max(s["approval_rate"] for s in stats.values())
        rows = ""
        for group, s in stats.items():
            ratio = s["approval_rate"] / top
            tone = "none" if ratio >= MIN_FAIRNESS_RATIO else ""
            rows += f"""
            <div class="giq-cov-row">
              <div class="giq-cov-name"><b>{escape(group)}</b><span>{s["n"]:,} applicants</span></div>
              <div class="giq-cov-bar" role="img" aria-label="{escape(group)} approval rate">
                <div style="width:{s["approval_rate"] * 100:.0f}%"></div></div>
              <div class="giq-cov-num"><b>{s["approval_rate"]:.1%}</b> approved</div>
              <div class="giq-cov-gaps fair {tone}">ratio {ratio:.2f},
              approved when repaid {s["tpr"]:.1%}</div>
            </div>"""
        st.html(
            f'<div class="giq-sub">By {escape(attr)}</div><div class="giq-cov"><div class="giq-cov-row '
            f'giq-cov-head"><div>Group</div><div>Approval rate</div><div>Rate</div><div>Ratio to highest '
            f"group</div></div>{rows}</div>"
        )
    st.html(check_list(evaluation.area_checks("Fairness")))

# ---------- Drift ----------
with drift_tab:
    st.markdown(
        f"The **population stability index (PSI)** compares this month's score distribution with the "
        f"validation set, in ten bins. Under {PSI_WATCH} is stable, {PSI_WATCH} to {PSI_ACT} means watch, "
        f"over {PSI_ACT} means act (re-validate or retrain). Current PSI: **{evaluation.psi:.3f}**, "
        f"{psi_band(evaluation.psi).lower()}."
    )
    frame = pd.DataFrame(evaluation.psi_bins)
    chart = frame.rename(columns={"expected": "Validation", "actual": spec.production_label}).set_index("bin")
    st.bar_chart(
        chart[["Validation", spec.production_label]] * 100,
        stack=False,
        color=["#14213D", "#E8A33D"],
        y_label="Share of scores (%)",
        x_label="Score bin",
        height=320,
    )
    st.dataframe(
        frame.assign(
            expected=lambda d: (d.expected * 100).round(1),
            actual=lambda d: (d.actual * 100).round(1),
            contribution=lambda d: d.contribution.round(4),
        ).rename(columns={"bin": "Score bin", "expected": "Validation %", "actual": "Production %",
                          "contribution": "PSI contribution"}),
        hide_index=True,
        width="stretch",
    )  # fmt: skip

# ---------- History ----------
with history_tab:
    if not validations:
        st.info(
            "No validation runs recorded yet. Record one from the Validation tab.", icon=":material/history:"
        )
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Run": v.code,
                        "Model": v.ai_system.name,
                        "Date": v.run_on,
                        "Validator": v.validator.full_name,
                        "Result": v.result,
                        "Failed checks": ", ".join(
                            m["name"] for m in json.loads(v.metrics_json) if not m["ok"]
                        )
                        or "None",
                        "Control tests": v.test_codes,
                    }
                    for v in validations
                ]
            ),
            hide_index=True,
            width="stretch",
        )
