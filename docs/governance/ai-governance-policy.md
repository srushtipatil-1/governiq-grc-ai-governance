# AI Governance Policy

**Kshitij Finserv Pvt Ltd (fictional)** · Owner: AI Governance Lead · Approved by: Risk & AI Governance
Committee · Version 1.0 · Review: yearly

> Sample policy written for the GovernIQ portfolio project. It is not legal advice and has not been adopted by
> any real organisation.

## 1. Purpose

To let Kshitij Finserv use AI to serve customers faster while keeping decisions about people fair, explainable,
secure and lawful, and to be able to prove it to the board, auditors and regulators.

## 2. Scope

Every AI system the company builds, buys or calls through an API, including models embedded in vendor
products, that supports a business process or interacts with customers, employees or job applicants.

## 3. Principles

1. **Accountable:** every AI system has a named business owner.
2. **Proportionate:** oversight scales with risk; high-risk uses get the strictest controls.
3. **Fair:** outcomes are tested across customer groups before release and monitored after.
4. **Transparent:** people are told when AI is involved and can ask for a human.
5. **Secure and private:** personal data is minimised and LLMs are tested against known attacks.
6. **Evidenced:** decisions, tests and approvals are recorded so they can be audited.

## 4. Roles

| Role | Responsibility |
| --- | --- |
| Risk & AI Governance Committee | Sets AI risk appetite, approves this policy, receives the quarterly pack |
| AI Governance Lead | Runs the programme, approves assessments and go-live, owns this policy |
| System owner | Accountable for the system's purpose, model card and corrective actions |
| GRC Analyst | Assesses systems, tests controls, validates models, independent of the owner |
| Internal Audit | Independently checks that this policy is followed |

## 5. Rules

### 5.1 Inventory and tiering
- Every AI system is registered before design work starts.
- Each system receives an external tier by purpose (prohibited, high, limited, minimal risk) and an internal
  tier (1 to 3) from its data, scale, decision impact and autonomy. The reasons are recorded.
- Prohibited uses, such as social scoring, are not built or bought.

### 5.2 Assessment and approval
- Tier 1 and 2 systems complete the NIST AI RMF-structured assessment before build.
- Every important gap becomes a risk in the enterprise risk register with an owner and a due date.
- The AI Governance Lead approves or rejects. The approver may not be the assessor or the system owner.

### 5.3 Lifecycle gates
- A system moves Design, Build, Validate, Deployed only through a recorded gate.
- Go-live requires: an approved assessment, a complete model card, no open audit findings on the controls
  that treat its risks, and human oversight for high-risk systems.

### 5.4 Validation and monitoring
- Models that decide on individuals are validated independently before release and yearly.
- Appetite: AUC at least 0.70; approval-rate ratio between groups at least 0.90 (the four-fifths rule,
  0.80, is treated as a floor, not a target); drift PSI above 0.25 triggers re-validation.
- Live systems are reviewed every 180 days (tier 1), 365 days (tier 2) or 730 days (tier 3).

### 5.5 Generative AI
- LLM applications are tested against the OWASP Top 10 for LLM Applications before release and after every
  significant change, and must pass 100% of the agreed suite.
- LLMs may only call read-only tools; any action that changes a customer record needs a human.
- Customer personal data is never used to train third-party models.

### 5.6 Transparency and redress
- Customers are told when they are talking to an AI and how to reach a person.
- Customers affected by an AI-supported decision can ask for a human review.

## 6. Exceptions

Exceptions are time-limited, approved by the AI Governance Lead, recorded as accepted risks and reported
to the Committee. No exception is allowed for prohibited uses.

## 7. Monitoring of this policy

Compliance is measured through the key risk indicators in GovernIQ (KRI-06 to KRI-10) and reported in the
quarterly committee pack.

## 8. Framework alignment

Structured with reference to ISO/IEC 42001, the NIST AI RMF 1.0, the RBI FREE-AI Committee recommendations
(Aug 2025), the DPDP Act 2023 and the OWASP Top 10 for LLM Applications 2025. Alignment is the author's
interpretation and is not a claim of conformity.
