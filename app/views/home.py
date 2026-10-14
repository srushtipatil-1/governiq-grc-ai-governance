"""Home page: what GovernIQ is, the audit trace, and the build roadmap."""

from html import escape

import streamlit as st

from governiq.config import DISCLAIMER, LIVE_MODULES, MODULES

# ---------- Hero: headline + the audit trace ----------
st.html(
    """
    <section class="giq-hero">
      <div>
        <h1>Every risk, traced to its proof.</h1>
        <p class="giq-lead">GovernIQ links each cyber, privacy and AI risk to the control that
        treats it, the test that checks it, the evidence that proves it and the action that fixes it.</p>
        <div class="giq-company">
          <div class="giq-mark">KF</div>
          <div><b>Kshitij Finserv Pvt Ltd</b><br>Fictional digital lending NBFC, Pune</div>
        </div>
      </div>

      <div class="giq-trace" role="img" aria-label="Sample audit trace from risk to corrective action">
        <div class="giq-trace-head"><h3>Audit trace</h3><span>Sample record</span></div>

        <div class="giq-node is-open">
          <div class="giq-dot"></div>
          <div><div class="giq-kind">Risk</div>
            <div class="giq-title">Former employees can still reach loan data</div>
            <div class="giq-id">RSK-004</div></div>
          <span class="giq-chip high">High, 16</span>
        </div>
        <div class="giq-node">
          <div class="giq-dot"></div>
          <div><div class="giq-kind">Control</div>
            <div class="giq-title">Quarterly user access review</div>
            <div class="giq-id">CTL-IAM-03 maps to ISO 27001 A.5.15, NIST CSF PR.AA-05</div></div>
          <span class="giq-chip plain">Key control</span>
        </div>
        <div class="giq-node is-fail">
          <div class="giq-dot"></div>
          <div><div class="giq-kind">Test</div>
            <div class="giq-title">2 of 25 sampled leavers still had access</div>
            <div class="giq-id">TEST-2026-Q3-014</div></div>
          <span class="giq-chip fail">Ineffective</span>
        </div>
        <div class="giq-node is-ok">
          <div class="giq-dot"></div>
          <div><div class="giq-kind">Evidence</div>
            <div class="giq-title">access_review_q3.xlsx</div>
            <div class="giq-id">sha256 9f2c41b7e3…a0e07a</div></div>
          <span class="giq-chip ok">Hash verified</span>
        </div>
        <div class="giq-node is-open">
          <div class="giq-dot"></div>
          <div><div class="giq-kind">Action</div>
            <div class="giq-title">Revoke leavers' access, then retest</div>
            <div class="giq-id">ACT-012, owner IT Operations</div></div>
          <span class="giq-chip open">Due 15 Nov</span>
        </div>
      </div>
    </section>
    """
)

# ---------- Two programmes, one spine ----------
st.html(
    """
    <h2 class="giq-section-title">Two programmes on one spine</h2>
    <p class="giq-section-lead">Cyber compliance and AI governance share the same risk register,
    control library, evidence store and findings tracker, so nothing is assessed twice.</p>
    <div class="giq-programmes">
      <div class="giq-prog">
        <h4>Cybersecurity and privacy</h4>
        <p>Risk register, control testing, evidence, vendor risk and audit packs for the
        information security programme.</p>
        <div class="giq-fw"><span>ISO/IEC 27001:2022</span><span>NIST CSF 2.0</span>
        <span>DPDP Act 2023 + Rules 2025</span></div>
      </div>
      <div class="giq-prog">
        <h4>AI governance</h4>
        <p>AI inventory, risk tiering, impact assessments, approval gates, model validation
        and LLM testing for four AI systems.</p>
        <div class="giq-fw"><span>ISO/IEC 42001</span><span>NIST AI RMF 1.0</span>
        <span>RBI FREE-AI</span><span>OWASP LLM Top 10</span></div>
      </div>
    </div>
    <div class="giq-fw-note">All mappings are partial and educational.</div>
    """
)

# ---------- Build roadmap ----------
stages = '<div class="giq-stage done"><div class="giq-pin"></div>'
stages += '<div class="giq-phase">Phase 1</div><div class="giq-name">Foundation</div></div>'
for name, phase in MODULES:
    state = "done" if name in LIVE_MODULES else ""
    stages += (
        f'<div class="giq-stage {state}"><div class="giq-pin"></div>'
        f'<div class="giq-phase">{escape(phase)}</div><div class="giq-name">{escape(name)}</div></div>'
    )
st.html(
    '<h2 class="giq-section-title" style="margin-top:48px">Build roadmap</h2>'
    '<p class="giq-section-lead">Each module goes live only after its tests pass.</p>'
    f'<div class="giq-road">{stages}</div>'
)

# ---------- Honest disclaimer ----------
st.html(f'<p class="giq-footnote">{escape(DISCLAIMER)}</p>')