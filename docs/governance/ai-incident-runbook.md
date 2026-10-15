# AI Incident Response Runbook

**Kshitij Finserv Pvt Ltd (fictional)** · Owner: AI Governance Lead · Works with the information security
incident process (CTL-IR-01) and evidences CTL-AI-11 (AI incidents logged, investigated and reported) · Synthetic example from the GovernIQ portfolio project

## What counts as an AI incident

Any event where an AI system causes or could cause harm, for example:

- The chatbot reveals another customer's data or its internal instructions.
- A model makes systematically unfair or wrong decisions (for example a fairness ratio below 0.80).
- An AI agent takes an action it was not allowed to take.
- Drift or a vendor model change makes outputs unreliable.
- A prompt-injection or data-poisoning attack is detected.

## Severity

| Severity | Examples | Response time |
| --- | --- | --- |
| **Sev 1** | Personal data of customers exposed; unauthorised financial action; harm to many people | Start within 1 hour, Committee chair informed the same day |
| **Sev 2** | Unfair or wrong decisions affecting a group; guardrail bypass without data loss | Start within 4 hours |
| **Sev 3** | Degraded accuracy, isolated wrong answer, failed monitoring check | Next working day |

## Roles

- **Incident lead:** AI Governance Lead (deputy: GRC Analyst)
- **System owner:** containment and technical fixes
- **Information Security:** forensics, logs, attacker activity
- **Privacy Office (DPO):** personal data assessment and DPDP breach notification
- **Communications:** customer and regulator messages, only after approval

## Steps

### 1. Detect and log (first 30 minutes)
- Record the incident in GovernIQ with time, system, reporter and what was seen.
- Preserve evidence: prompts and responses, model version, logs, screenshots. Hash files on upload.

### 2. Contain
- Use the system's tested kill switch or rollback: switch the chatbot to human hand-off, revert
  the model to the last validated version, or disable the agent's tools.
- For a high-risk decision model, move affected decisions to full manual review.

### 3. Assess
- How many people are affected, what data, since when?
- If personal data was exposed, the DPO decides on notification to the Data Protection Board and affected
  people under the DPDP Act and Rules, within the required time.
- Decide whether regulators or partners must be informed.

### 4. Fix and verify
- Correct the cause: new guardrail, retrained model, tighter permissions, vendor escalation.
- Add the attack or failure as a **new test case** (for example in the OWASP LLM suite) so it can never
  silently return.
- Re-run validation or the red-team suite; record the result as a control test.

### 5. Recover
- Return to normal operation only through the lifecycle gate, with the AI Governance Lead's approval.

### 6. Learn (within 10 working days)
- Write a blameless review: timeline, root cause, what worked, what did not.
- Raise findings and corrective actions with owners and due dates; track them to closure.
- Update the model card, the risk register and, if needed, this runbook.

## Checklist

- [ ] Incident logged and severity set
- [ ] Evidence preserved and hashed
- [ ] System contained (kill switch, rollback or manual review)
- [ ] Impact assessed; DPO decision on notification recorded
- [ ] Fix deployed and verified by a passing test
- [ ] New regression test added
- [ ] Review written; actions tracked in GovernIQ
