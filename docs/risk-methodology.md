# Risk methodology

GovernIQ scores every risk, cyber, privacy or AI, with the same 5x5 method.

## 1. Likelihood scale (how likely in the next 12 months)

| Score | Level | Meaning |
| --- | --- | --- |
| 1 | Rare | Less than 5% chance; no history of it happening |
| 2 | Unlikely | 5-20%; has happened elsewhere in the industry |
| 3 | Possible | 20-50%; has happened here once in the past 3 years |
| 4 | Likely | 50-80%; happened here in the past year |
| 5 | Almost certain | Over 80%; happening now or expected soon |

## 2. Impact scale (how bad if it happens)

| Score | Level | Financial | Customers / people | Regulatory |
| --- | --- | --- | --- | --- |
| 1 | Minimal | Under Rs 1 lakh | No customer affected | None |
| 2 | Minor | Rs 1-10 lakh | Under 100 customers | Internal finding only |
| 3 | Moderate | Rs 10 lakh-1 crore | 100-10,000 customers | Regulator query |
| 4 | Major | Rs 1-10 crore | 10,000-1 lakh customers, or unfair decisions on people | Regulatory breach reported |
| 5 | Severe | Over Rs 10 crore | Over 1 lakh customers | Penalty, licence action, public news |

When a risk has several impact types, use the **highest** one.

## 3. Risk score and rating

Inherent score = Likelihood x Impact (range 1 to 25)

| Score | Rating | Required response |
| --- | --- | --- |
| 20-25 | Critical | Treatment plan within 7 days; only the CRO can accept it |
| 10-16 | High | Treatment plan within 30 days; CISO can accept it |
| 5-9 | Medium | Owner decides treatment; reviewed every quarter |
| 1-4 | Low | Accept and monitor; reviewed every year |

## 4. Inherent vs residual risk

- **Inherent risk:** the score *before* considering controls.
- **Residual risk:** the score *after* the linked controls work.

The analyst re-rates residual likelihood and impact. GovernIQ enforces two rules:

1. Residual score can never be higher than inherent score.
2. Residual score can be lower than inherent **only if** at least one linked control
   has passed its latest operating effectiveness test.

Why rule 2: the most common audit finding in real risk registers is claiming
lower risk because of controls that were never tested.

## 5. Treatment options

| Option | Meaning | Example |
| --- | --- | --- |
| Mitigate | Add or improve controls | Enforce MFA on LoanCore |
| Transfer | Shift impact to another party | Cyber insurance, vendor contract clauses |
| Avoid | Stop the activity | Retire an unsafe AI feature |
| Accept | Live with it, with sign-off | Low risk accepted by owner |

Every risk has one named owner and a due date for its treatment.

## 6. Review cycle

- Critical and High risks: reviewed monthly
- Medium: quarterly
- Low: yearly
- Any risk is re-rated immediately after an incident, a failed control test or a red KRI.

## 7. Limitations (stated honestly)

- A 5x5 matrix multiplies ordinal labels, so a score of 12 is not exactly "twice as bad" as 6.
  It is a tool for prioritising, not a precise measurement.
- Residual ratings depend on analyst judgement.
- Future improvement: quantitative methods such as FAIR.