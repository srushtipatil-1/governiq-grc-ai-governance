# GovernIQ

**Every risk, traced to its proof.** An integrated GRC and AI governance platform, built as a portfolio project
for a fictional Indian digital lender.

[![CI](https://github.com/srushtipatil-1/governiq-grc-ai-governance/actions/workflows/ci.yml/badge.svg)](https://github.com/srushtipatil-1/governiq-grc-ai-governance/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-14213D)
![Tests](https://img.shields.io/badge/tests-238%20passing-1F7A6E)
![Data](https://img.shields.io/badge/data-synthetic%20only-E8A33D)

**Live demo:** LIVE_URL (one-click demo roles on the sign-in page; the demo resets on restart)

![GovernIQ home page with the audit trace](docs/screenshots/00-home.png)

> Educational portfolio project using synthetic data. It is not a certification, a conformity assessment, or
> proof that any organisation complies with ISO/IEC 27001, ISO/IEC 42001, NIST, DPDP or any other framework.

---

## The problem it solves

A regulated lender has to answer two questions with evidence, not opinions:

1. **Do our security and privacy controls actually work?** Auditors want the risk, the control, the test,
   the evidence and the fix linked together, not five spreadsheets that disagree.
2. **Are our AI systems safe to use on customers?** The credit model must be fair, the chatbot must not leak
   data, and nothing should go live without an independent assessment and sign-off.

Most teams run these as two separate programmes. GovernIQ puts both on **one spine**: one risk register,
one control library mapped to seven frameworks, one evidence store, one findings tracker and one
tamper-evident audit trail.

**The company:** *Kshitij Finserv Pvt Ltd*, a fictional NBFC in Pune with 30 risks, 33 controls and four AI
systems: **CreditLens** (credit scoring), **FraudShield** (vendor fraud model), **Sahayak** (LLM customer
chatbot) and **TalentSift** (CV screening).

## What it does

| Module | What you can do | How it works |
| --- | --- | --- |
| **Risk register** | Add, filter and trace 30 cyber, privacy, vendor and AI risks on a 5x5 heat map | Likelihood x impact scoring with fixed bands. Residual risk can only drop below inherent if a linked control has **passed an operating test**. |
| **Controls & mapping** | One library of 33 controls mapped to 85 requirements in 7 frameworks; Risk & Control Matrix export | "Test once, comply many": a control maps to ISO 27001, NIST CSF, DPDP and AI frameworks at once. Coverage gaps are listed, not hidden. |
| **Testing & findings** | Record design and operating tests with evidence; run 5 automated control checks | Evidence gets a SHA-256 fingerprint. A failed test opens a finding automatically; it closes only when its actions are done **and** a retest passes. Tester, reviewer and control owner must be different people. |
| **Automated checks** | Test the full population from system exports (leavers, MFA, backups, patches, access reviews) | Finds a leaver with an active account and a privileged account without MFA, and records them as control tests. |
| **AI governance** | AI inventory, purpose-based risk tiering, a 16-question NIST AI RMF assessment and approval | Tiering follows EU AI Act-style purpose rules and shows **why** (CreditLens and TalentSift: high risk). Gaps become AI risks in the register. The approver cannot be the assessor or the owner. |
| **AI lifecycle** | Stage gates from Design to Deployed, versioned model cards, post-launch reviews | Go-live needs an approved assessment, a complete model card and no open findings. Sahayak is blocked, with the three reasons shown. |
| **Model risk** | Validate CreditLens: AUC, precision, fairness by gender and region, drift (PSI) | Plain-Python metrics on 2,000 hold-out cases. Gender approval ratio 0.85 fails the 0.90 appetite but meets the four-fifths floor. Results become control tests. |
| **GenAI assurance** | Red-team Sahayak with 16 prompts mapped to the OWASP Top 10 for LLM Applications (2025) | 2/16 pass without guardrails, 16/16 with 11 layered guardrails. LLM03 and LLM04 are reported as gaps because prompts cannot test them. |
| **Dashboard** | 11 key risk indicators, a 2-page committee PDF and an audit evidence ZIP | KRIs have owners and amber/red thresholds. The audit pack carries a SHA-256 manifest of every file. |
| **Audit trail & users** | Sign in, role permissions, verify and export the audit trail | Passwords are salted scrypt hashes with lockout. Every change is hash-chained, so editing or deleting a past entry is detected and located. |

<details>
<summary><b>Screenshots</b></summary>

| | |
| --- | --- |
| ![Dashboard](docs/screenshots/01-dashboard.png) | ![Risk heat map](docs/screenshots/02-risk-heatmap.png) |
| Dashboard and KRIs | Risk heat map |
| ![Framework coverage](docs/screenshots/03-framework-coverage.png) | ![Automated checks](docs/screenshots/04-automated-checks.png) |
| Framework coverage | Automated control checks |
| ![AI inventory](docs/screenshots/05-ai-inventory.png) | ![Lifecycle gates](docs/screenshots/06-lifecycle-gates.png) |
| AI inventory and tiers | Go-live gate |
| ![Fairness](docs/screenshots/07-model-fairness.png) | ![GenAI red team](docs/screenshots/08-genai-redteam.png) |
| Model fairness | LLM red-team, with and without guardrails |
| ![Audit trail](docs/screenshots/09-audit-trail.png) | ![Sign in](docs/screenshots/00-sign-in.png) |
| Hash-chained audit trail | Sign-in with demo roles |

</details>

## One record, end to end

The trace the home page shows is real data you can click through:

```
RSK-004  Former employees can still reach loan data         (High, 16)
  └─ CTL-IAM-02  Leaver access removed within 24 hours      ISO 27001 A.5.18 · NIST CSF PR.AA-05 · DPDP
       └─ TST-002  Operating test, 25 sampled, 2 exceptions  -> Ineffective
            ├─ EV-0002  work paper, sha256 e6e5422e...        -> fingerprint verified
            └─ FND-001  opened automatically
                 └─ ACT-001  disable accounts, automate HRMS exits (due 15 Nov)
CCM-01 automated check on the full population later finds 1 more leaver still active.
```

## Frameworks and how far the mapping goes

| Framework | Requirements mapped | Claim level |
| --- | --- | --- |
| ISO/IEC 27001:2022 Annex A | 20 | Partial mapping |
| NIST Cybersecurity Framework 2.0 | 19 | Partial mapping |
| DPDP Act 2023 and DPDP Rules 2025 | 8 | Framework-inspired |
| ISO/IEC 42001:2023 Annex A | 11 | Partial mapping |
| NIST AI Risk Management Framework 1.0 | 11 | Framework-inspired |
| RBI FREE-AI Committee recommendations (Aug 2025) | 6 | Framework-inspired |
| OWASP Top 10 for LLM Applications 2025 | 10 | Partial mapping |

Requirement titles are short paraphrases written for this project, not the standards' text.

## Rules enforced in code (not just written in a policy)

- A tester cannot test a control they own; a reviewer cannot be the tester or the owner.
- Test results come from the exceptions found; nobody types "Effective".
- Residual risk below inherent requires a linked control whose latest operating test passed.
- A finding closes only when every action is done and a later operating test passes.
- An AI assessment is approved only by the AI Governance Lead, never by its assessor or the system owner.
- A system goes live only through a gate whose checklist is stored with the decision.
- Every change writes a hash-chained audit entry; verification names the first broken entry.

## Tech stack

Python 3.12+, Streamlit (UI), SQLAlchemy with SQLite (data), openpyxl (Excel), ReportLab (PDF), pytest
(238 tests), ruff, bandit and pip-audit in GitHub Actions, Docker. No paid services and no external AI API:
the Sahayak chatbot is a rule-based stand-in so the LLM tests are repeatable offline.

## Run it locally

```bash
git clone https://github.com/srushtipatil-1/governiq-grc-ai-governance.git
cd governiq-grc-ai-governance
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
python scripts/seed_db.py       # builds the synthetic demo database
pytest -q                       # 238 tests
streamlit run app/Home.py
```

Sign in with a demo role button, or type a username such as `priya.analyst` with the demo password shown on
the sign-in page. Docker and Streamlit Cloud steps are in [docs/deployment.md](docs/deployment.md).

## Project structure

```
app/            Streamlit router (Home.py), pages (views/) and styles
governiq/       All logic: risks, controls, assurance, automation, ai_governance, lifecycle,
                model_risk, genai, reporting, auth, audit (pages only call these)
data/seed/      Synthetic CSVs: users, risks, controls, framework requirements, AI systems,
                system exports, model scores, LLM test prompts
tests/          238 pytest tests, including page tests with Streamlit AppTest
docs/           Deployment guide, governance documents and screenshots
```

## Governance documents

Written for the fictional company to show the policy side of the same programme:

- [AI governance policy](docs/governance/ai-governance-policy.md)
- [Executive memo to the Risk Committee](docs/governance/executive-memo.md)
- [AI incident response runbook](docs/governance/ai-incident-runbook.md)

## Honest limitations

- Synthetic data and a fictional company; numbers illustrate the method, not a real organisation.
- The chatbot is a deterministic stand-in, so the guardrails are tested against known attack patterns, not
  against a live model. Pattern filters can be bypassed by new phrasings.
- One shared demo password and one-click demo sign-in keep the public demo usable; a real deployment would
  switch demo mode off, use single sign-on and a server database.
- Framework mappings are partial and paraphrased; they show the method, not complete coverage.

## Author

Built by **Srushti Patil** as a learning and portfolio project in GRC and AI governance.
