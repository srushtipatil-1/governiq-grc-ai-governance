# AI assessment method

Every AI system at Kshitij Finserv goes through four steps:
**Register -> Classify -> Assess -> Approve**, then it is monitored while live.

## 1. Register (AI inventory)

Each AI system is recorded with: name, purpose, business owner, technical owner,
built or bought, vendor, model type, personal data used, people affected,
level of human oversight, and lifecycle stage.

## 2. Classify (two tiers)

### 2a. External tier (EU AI Act-style, used as a classification method only)

Rules are checked in order; the first rule that matches decides the tier.

| Order | Rule | Tier |
| --- | --- | --- |
| 1 | Uses a prohibited practice (e.g. social scoring, manipulative techniques) | Prohibited: stop |
| 2 | Decides on credit for individuals, recruitment, education access or similar listed uses | High risk |
| 3 | Talks directly to people or generates content (e.g. a chatbot) | Limited risk: transparency duties |
| 4 | None of the above | Minimal risk |

Note: fraud detection is excluded from the EU AI Act's credit-scoring high-risk use.
GovernIQ shows *which rule fired*, because an auditor will always ask why.

### 2b. Internal tier (1 to 3, firm-specific)

| Factor | Raises the tier when... |
| --- | --- |
| Personal data | It uses personal or sensitive data (DPDP) |
| Scale | It affects more than 10,000 people |
| Autonomy | It decides without a human reviewing each decision |
| Reversibility | Its decisions are hard to undo (e.g. a loan rejection) |

Tier 1 = highest scrutiny. Tier 1 systems need committee approval and yearly revalidation.

### Expected results for the four systems

| AI system | External tier | Reason |
| --- | --- | --- |
| CreditLens | High risk | Credit decisions on individuals |
| TalentSift | High risk | Recruitment decisions |
| Sahayak | Limited risk | Chatbot talking to customers |
| FraudShield | Minimal risk (internal tier still high) | Fraud detection is excluded from the credit category, but it affects many customers |

## 3. Assess (NIST AI RMF-structured questionnaire)

About 30 questions grouped by the four NIST AI RMF functions:

| Function | Example question |
| --- | --- |
| Govern | Is there a named owner accountable for this system? |
| Map | Is the intended purpose and its limits documented? |
| Measure | Has fairness been tested across groups (e.g. gender, region)? |
| Manage | Is there a process to switch off or roll back the system? |

Each question is tagged to a trustworthiness characteristic: valid and reliable;
safe; secure and resilient; accountable and transparent; explainable and interpretable;
privacy-enhanced; fair with harmful bias managed.

A "No" or "Partial" on an important question automatically creates a **risk**
in the shared risk register, scored with the normal risk methodology.

## 4. Approve (lifecycle gates)

Design -> Build -> Validate -> **Deploy** -> Monitor -> Retire

To move to Deploy, a system needs:
1. A completed assessment
2. A completed DPIA if it uses personal data
3. Independent validation (for Tier 1 systems)
4. Approval by a **different person** from the assessor (segregation of duties)

A post-implementation review happens 30 days after deployment.

## 5. Monitor

- Performance and drift checks on a schedule
- Fairness metric: disparate impact ratio; below 0.8 opens an incident
- AI incidents are logged and linked to risks and findings
- LLM systems (Sahayak) are tested against OWASP Top 10 for LLM Applications 2025

## Limitations

- Classification is rule-based and simplified; real legal classification needs legal review.
- Fairness is tested on synthetic data with one metric family.
- This is a framework-inspired method, not a conformity assessment.