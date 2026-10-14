# GovernIQ — Integrated GRC & AI Governance Platform

**Every risk, traced to its proof.** GovernIQ links each cyber, privacy and AI risk to the control
that treats it, the test that checks it, the evidence that proves it and the action that fixes it.

> **Disclaimer:** Educational portfolio project using synthetic data. It is not a certification,
> a conformity assessment, or proof that any organisation complies with ISO/IEC 27001,
> ISO/IEC 42001, NIST, DPDP or any other framework.

## Status

Phase 1 complete: project foundation, home page, automated tests and code checks.
More modules are being built phase by phase.

## Scenario

Kshitij Finserv Pvt Ltd (fictional), a digital lending NBFC in Pune, managing cybersecurity,
privacy and AI risk in one traceable system.

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app/Home.py
```

## Run the tests

```bash
pytest -v
ruff check .
```

## Tech stack

Python, Streamlit, pytest, ruff.