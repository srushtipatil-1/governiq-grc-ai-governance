"""GenAI assurance: run the OWASP LLM Top 10 test suite against Sahayak, with and without guardrails."""

from html import escape

import pandas as pd
import streamlit as st
from sqlalchemy import select

from governiq.genai import (
    MAX_INPUT_CHARS,
    MAX_OUTPUT_CHARS,
    SahayakStub,
    load_cases,
    owasp_coverage,
    record_red_team,
    run_suite,
)
from governiq.models import User
from governiq.ui import current_actor, get_session

GUARDRAILS = (
    (
        "Input size limit",
        "LLM10",
        f"Rejects messages over {MAX_INPUT_CHARS:,} characters before they reach the model.",
    ),
    ("Injection filter", "LLM01, LLM07", "Blocks known instruction-override and prompt-extraction patterns."),
    ("Data access scope", "LLM02, LLM08", "The bot can only see the signed-in customer's own records."),
    ("Action allowlist", "LLM06", "Only read-only tools run; changes become a request for a human agent."),
    ("Scope policy", "LLM09", "No promises of approval; decisions belong to the credit process."),
    ("FAQ grounding", "LLM09", "Product facts come only from approved FAQ content, not free generation."),
    (
        "Retrieval filter",
        "LLM08, LLM01",
        "Retrieved documents must come from trusted sources and the right owner.",
    ),
    ("Canary detector", "LLM07", "A secret marker in the system prompt; if it appears in output, block it."),
    ("PII redaction", "LLM02", "Masks PAN, phone and Aadhaar patterns in anything the bot says."),
    ("Output encoding", "LLM05", "HTML-escapes output so a script can never run in the chat window."),
    ("Output budget", "LLM10", f"Caps replies at {MAX_OUTPUT_CHARS} characters and refuses bulk repetition."),
)

session = get_session()
actor = session.scalar(select(User).where(User.username == current_actor()))
cases = load_cases()
unguarded = run_suite(SahayakStub(guardrails=False), cases)
guarded = run_suite(SahayakStub(guardrails=True), cases)

st.html(
    f"""
    <div class="giq-page-head">
      <h1>GenAI assurance</h1>
      <p>{len(cases)} attack and baseline prompts mapped to the OWASP Top 10 for LLM Applications (2025),
      run against Sahayak. Without guardrails {sum(r.passed for r in unguarded)} of {len(cases)} pass; with
      guardrails {sum(r.passed for r in guarded)} of {len(cases)} pass. Sahayak here is a rule-based stand-in
      for the vendor LLM, so results are repeatable offline.</p>
    </div>
    """
)

if "genai_flash" in st.session_state:
    kind, message = st.session_state.pop("genai_flash")
    (st.success if kind == "ok" else st.warning)(message, icon=":material/info:")

suite_tab, try_tab, coverage_tab, guard_tab = st.tabs(
    ["Red-team suite", "Try a prompt", "OWASP coverage", "Guardrails"]
)

# ---------- Red-team suite ----------
with suite_tab:
    on = st.toggle("Guardrails on", value=True, help="Switch off to see what an unprotected chatbot does.")
    results = guarded if on else unguarded
    failed = [r for r in results if not r.passed]
    (st.success if not failed else st.error)(
        f"{len(results) - len(failed)} of {len(results)} cases pass with guardrails {'on' if on else 'off'}."
        + (f" Failing: {', '.join(r.case.id for r in failed)}." if failed else ""),
        icon=":material/shield:" if not failed else ":material/gpp_bad:",
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Case": r.case.id,
                    "OWASP": r.case.owasp,
                    "Attack": r.case.title,
                    "Result": "Pass" if r.passed else "Fail",
                    "Why": r.reason,
                    "Guardrails used": ", ".join(r.reply.guardrails) or "-",
                    "Reply": r.reply.text[:160],
                }
                for r in results
            ]
        ).style.map(
            lambda v: (
                "background-color:#DCEFEA;color:#17605A;font-weight:600"
                if v == "Pass"
                else "background-color:#F6DDE0;color:#8E2433;font-weight:600"
            ),
            subset=["Result"],
        ),
        hide_index=True,
        width="stretch",
        height=36 * (len(results) + 1) + 3,
    )
    st.caption(
        "Recording the run saves one automated operating test on CTL-AI-09 (LLM testing) and one on "
        "CTL-AI-10 (agent permissions), with the results file as evidence. A pass can close FND-004 once "
        "its action is done."
    )
    if st.button("Record run as control tests", type="primary", icon=":material/fact_check:"):
        try:
            recorded = record_red_team(session, actor.username, guardrails=on)
        except ValueError as problem:
            st.error(f"Not recorded. {problem}", icon=":material/block:")
        else:
            parts = []
            for _, outcome in recorded:
                text = f"{outcome.test.code} on {outcome.test.control.code}: {outcome.test.result}"
                if outcome.opened:
                    text += f", opened {outcome.opened.code}"
                text += "".join(f", closed {f.code}" for f in outcome.closed)
                text += "".join(
                    f", {f.code} stays open until its actions are done" for f in outcome.still_open
                )
                parts.append(text)
            st.session_state["genai_flash"] = ("ok", "Recorded " + "; ".join(parts) + ".")
            st.rerun()

# ---------- Try a prompt ----------
with try_tab:
    example = st.selectbox(
        "Start from an attack in the suite", cases, format_func=lambda c: f"{c.id} {c.owasp}: {c.title}"
    )
    prompt = st.text_area("Prompt", value=example.prompt[:400], height=90, key=f"prompt-{example.id}")
    left, right = st.columns(2)
    for column, label, bot in (
        (left, "Without guardrails", SahayakStub(False)),
        (right, "With guardrails", SahayakStub(True)),
    ):
        reply = bot.respond(prompt)
        with column.container(border=True):
            st.markdown(f"**{label}**")
            st.html(
                f'<p style="font-size:15px;margin:0;word-break:break-word">{escape(reply.text[:700])}</p>'
            )
            st.caption(
                ("Guardrails: " + ", ".join(reply.guardrails) if reply.guardrails else "No guardrail acted.")
                + (f" Tools called: {', '.join(reply.tool_calls)}." if reply.tool_calls else "")
            )

# ---------- OWASP coverage ----------
with coverage_tab:
    rows = owasp_coverage(session, cases)
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "OWASP": r.ref,
                    "Risk": r.title,
                    "Prompt tests": r.cases,
                    "Mapped controls": ", ".join(r.controls) or "-",
                    "Coverage": r.coverage,
                }
                for r in rows
            ]
        ),
        hide_index=True,
        width="stretch",
        height=36 * (len(rows) + 1) + 3,
    )
    gaps = [r.ref for r in rows if r.coverage == "Gap"]
    if gaps:
        st.warning(
            f"{', '.join(gaps)} are supply-chain and poisoning risks: prompts cannot test them. They need "
            "process controls (vendor model assessment, training-data provenance) that are not mapped "
            "yet, so they are reported as gaps rather than hidden.",
            icon=":material/report:",
        )

# ---------- Guardrails ----------
with guard_tab:
    items = "".join(
        f'<li class="ok"><div><b>{escape(owasp)}</b>{escape(name)}<br><small>{escape(what)}</small></div>'
        f"<span>{escape(name.split()[0])}</span></li>"
        for name, owasp, what in GUARDRAILS
    )
    st.html(f'<div class="giq-res"><ul>{items}</ul></div>')
    st.caption(
        "Layered defence: no single filter is trusted on its own. Pattern filters can be bypassed by new "
        "phrasings, so the suite should grow with every incident and every new attack technique."
    )
