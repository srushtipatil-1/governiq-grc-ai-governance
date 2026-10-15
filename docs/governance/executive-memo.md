# Memo: AI and control risk position, October 2026

**To:** Risk & AI Governance Committee, Kshitij Finserv Pvt Ltd (fictional)
**From:** GRC and AI Governance team
**Classification:** Internal · synthetic example from the GovernIQ portfolio project

## Bottom line

Our controls are only partly proven and two AI risks need a decision this month. Five of eleven key risk
indicators are red. None of them is a breach today, but each is a gap an auditor or regulator would find.

## What needs your decision

1. **CreditLens fairness.** Women are approved 47.8% of the time against 56.0% for men, a ratio of 0.85. That
   meets the 0.80 four-fifths floor but misses our own 0.90 appetite. **Decide** whether CreditLens
   continues with full manual review of declined female applicants while the model is retrained, or is
   paused for that segment.
2. **Privileged access.** One privileged service account has no MFA and one leaver still has an active
   account, both found by automated checks on full system exports. **Direct** IT Operations to fix both
   within 24 hours and enforce MFA with no service-account exceptions.
3. **AI go-live discipline.** Sahayak (customer chatbot) and TalentSift (CV screening) are not cleared for
   launch. **Confirm** that no AI system goes live without passing its gate.

## Where we stand

| Area | Position | Trend |
| --- | --- | --- |
| Risk register | 30 risks; 20 critical or high before controls, 17 after | Improving as controls are tested |
| Control assurance | 9 of 33 controls tested, 6 proven effective; 59% of key controls untested | Testing plan in place |
| Findings | 4 open, all high severity; no actions overdue yet | Watch: three actions fall due by mid-December |
| AI portfolio | 4 systems, 2 live; 1 high-risk system unassessed; 1 post-launch review overdue | Needs action |
| GenAI security | Sahayak passes 16 of 16 OWASP LLM tests with guardrails, 2 of 16 without | Guardrails effective on known attacks |
| Audit trail | Hash chain verified, no tampering detected | Stable |

## Why this matters

- **Regulatory:** the DPDP Act and the RBI's direction on responsible AI both expect evidence of fair,
  secure processing, not policy statements.
- **Customer:** an unfair credit model or a chatbot that leaks data is a conduct and reputation issue.
- **Audit:** untested key controls mean residual risk cannot be reduced on paper.

## Next 90 days

1. Test the 13 untested key controls, starting with access management and change control.
2. Complete the TalentSift assessment and the overdue FraudShield post-launch review.
3. Retrain and re-validate CreditLens; report the fairness ratio monthly.
4. Close FND-004 by completing ACT-004 and re-running the Sahayak red-team suite.

Supporting detail: GovernIQ dashboard, committee pack PDF and audit evidence pack.
