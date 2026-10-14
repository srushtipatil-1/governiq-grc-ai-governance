# Scenario: Kshitij Finserv Pvt Ltd (fictional)

> Fictional company created for this educational project. Any resemblance to a real company is accidental.

## The company

| Item | Detail |
| --- | --- |
| Business | Digital lending NBFC: personal loans and small business loans through a mobile app |
| Location | Pune, India |
| Size | About 600 employees, 1.2 million customers |
| Regulator | Reserve Bank of India (RBI) |
| Personal data held | Names, PAN, Aadhaar-linked KYC, bank statements, income, phone, location |

## Why it needs GovernIQ

1. It wants ISO/IEC 27001 certification next year and needs audit-ready evidence.
2. DPDP Rules 2025 obligations apply from May 2027, so it must prepare now.
3. It uses four AI systems with no central inventory, no risk tiering and no approval process.
4. Today, risks, control tests and evidence sit in separate spreadsheets and email folders.

## Key systems (assets)

| System | Purpose | Holds personal data? |
| --- | --- | --- |
| LoanCore | Loan management system | Yes |
| KYC Vault | Identity documents storage | Yes |
| Customer mobile app | Loan applications | Yes |
| HRMS | Employee records | Yes |
| Cloud platform | Hosts all applications | Yes |

## AI systems

| AI system | What it does | Built or bought | Who it affects |
| --- | --- | --- | --- |
| CreditLens | Scores loan applicants and recommends approve or reject | Built in-house (ML model) | Loan applicants |
| FraudShield | Flags suspicious transactions | Bought from a vendor | Customers |
| Sahayak | GenAI chatbot answering customer questions | Built on a third-party LLM API | Customers |
| TalentSift | Screens job applicants' resumes | Bought (SaaS tool) | Job applicants |

## People and roles

| Role | Responsibility |
| --- | --- |
| CISO | Owns the information security programme |
| GRC Analyst | Maintains risks, controls, tests and findings |
| Control Owners | IT, HR and Engineering managers who run controls |
| AI Governance Committee | Approves high-risk AI systems before go-live |
| Internal Audit | Reviews everything independently, changes nothing |

## Frameworks in scope

ISO/IEC 27001:2022, NIST CSF 2.0, DPDP Act 2023 + Rules 2025, ISO/IEC 42001,
NIST AI RMF 1.0, RBI FREE-AI recommendations, OWASP Top 10 for LLM Applications 2025.
All mappings in GovernIQ are partial and educational.