# Roles and access

GovernIQ follows **least privilege**: each role gets only the access it needs.

## 1. Roles

| Role | Real-world equivalent | Purpose |
| --- | --- | --- |
| Admin | GRC tool administrator | Manages users and reference data; does no GRC work |
| GRC Analyst | Risk and compliance analyst | Maintains risks, controls, tests, findings, vendors |
| Control Owner | IT, HR or Engineering manager | Uploads evidence and updates their own actions |
| AI Governance Lead | Chair of the AI Governance Committee | Assesses and approves AI systems |
| Auditor | Internal or external auditor | Reads and exports everything, changes nothing |

## 2. Access matrix

R = read, C = create, U = update, A = approve, E = export, - = no access

| Area | Admin | GRC Analyst | Control Owner | AI Gov Lead | Auditor |
| --- | --- | --- | --- | --- | --- |
| Users and roles | CRU | - | - | - | R |
| Risk register | R | CRU | R (own) | R | RE |
| Controls and mappings | R | CRU | R (own) | R | RE |
| Control tests | R | CRU | R (own) | R | RE |
| Evidence | R | CRU | CRU (own) | R | RE |
| Findings and actions | R | CRU | U (own actions) | R | RE |
| AI inventory | R | CRU | R | CRUA | RE |
| AI assessments | R | CRU | - | CRUA | RE |
| Audit log | R | R | - | R | RE |
| Reports and exports | E | E | - | E | E |

## 3. Segregation of duties rules (enforced in code)

1. The person who **performs** a control test cannot **review** it.
2. The person who **assesses** an AI system cannot **approve** it.
3. A Control Owner cannot **close** a finding on their own control; a GRC Analyst must verify the retest.
4. Nobody can edit or delete the **audit log**, including the Admin.
5. The Admin cannot approve anything, because administrators should not also do the business work.

## 4. Why the Auditor is read-only

An auditor must be independent. If an auditor could change records, nobody could trust the audit.

## 5. Demo accounts (synthetic)

| Username | Role |
| --- | --- |
| admin.demo | Admin |
| priya.analyst | GRC Analyst |
| rahul.itops | Control Owner (IT Operations) |
| meera.aigov | AI Governance Lead |
| arjun.audit | Auditor |

Passwords are never stored in plain text; they are hashed with bcrypt (Phase 11).