"""Reporting: key risk indicators, the risk committee pack (PDF) and the audit evidence pack (ZIP).

Every number here is computed from the same records the other modules write, so the dashboard, the
committee pack and the audit pack can never disagree with each other.
"""

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from governiq.ai_governance import latest_assessment, load_ai_systems, load_assessments
from governiq.assurance import (
    effective_controls,
    evidence_dir,
    latest_operating_results,
    load_findings,
    load_tests,
)
from governiq.audit import audit_csv, verify_chain
from governiq.automation import (
    EXPORTS_TAKEN_ON,
    SYSTEMS_DIR,
    leavers_with_active_accounts,
    privileged_accounts_without_mfa,
)
from governiq.config import APP_NAME, DISCLAIMER
from governiq.controls import load_controls, rcm_workbook
from governiq.genai import SahayakStub, run_suite
from governiq.lifecycle import next_review_due, review_status, reviews_for
from governiq.model_risk import evaluate, load_validations
from governiq.models import Action, Control
from governiq.risks import load_risks, rating_for, risk_rows

COMPANY = "Kshitij Finserv Pvt Ltd (fictional)"
RAG_ORDER = {"Red": 0, "Amber": 1, "Green": 2}


# ---------------------------------------------------------------- key risk indicators
@dataclass
class KRI:
    code: str
    name: str
    area: str  # Cyber, Assurance or AI
    value: float
    display: str
    amber: float
    red: float
    higher_is_worse: bool = True
    owner: str = ""
    note: str = ""

    @property
    def rag(self) -> str:
        if self.higher_is_worse:
            return "Red" if self.value >= self.red else "Amber" if self.value >= self.amber else "Green"
        return "Red" if self.value < self.red else "Amber" if self.value < self.amber else "Green"

    @property
    def threshold(self) -> str:
        sign = ">=" if self.higher_is_worse else "<"
        if self.amber == self.red:  # zero-tolerance indicator: any occurrence is red
            return f"Red {sign} {self._fmt(self.red)}"
        return f"Amber {sign} {self._fmt(self.amber)}, Red {sign} {self._fmt(self.red)}"

    def _fmt(self, v: float) -> str:
        if "%" in self.display:
            return f"{v:.0f}%"
        return f"{v:g}"


def compute_kris(session: Session, today: date | None = None) -> list[KRI]:
    today = today or date.today()
    risks = load_risks(session)
    working = effective_controls(session)
    high = [r for r in risks if r.inherent_score >= 10]
    unproven = [r for r in high if not any(c.code in working for c in r.controls)]
    pct_unproven = 100 * len(unproven) / len(high) if high else 0.0

    overdue_actions = session.scalars(
        select(Action).where(Action.status == "Open", Action.due_date < today)
    ).all()

    key_controls = session.scalars(select(Control).where(Control.is_key)).all()
    tested = latest_operating_results(session)
    untested = [c for c in key_controls if c.code not in tested]
    pct_untested = 100 * len(untested) / len(key_controls) if key_controls else 0.0

    leavers = leavers_with_active_accounts(SYSTEMS_DIR, EXPORTS_TAKEN_ON)
    no_mfa = privileged_accounts_without_mfa(SYSTEMS_DIR, EXPORTS_TAKEN_ON)

    systems = load_ai_systems(session)
    assessments = load_assessments(session)
    high_ai = [s for s in systems if s.external_tier == "High risk" and s.lifecycle_stage != "Retired"]
    unassessed = [
        s for s in high_ai if (a := latest_assessment(assessments, s)) is None or a.status != "Approved"
    ]
    overdue_pir = [
        s for s in systems if review_status(next_review_due(s, reviews_for(session, s)), today) == "Overdue"
    ]

    model = evaluate("AI-01")
    gender = next(c for c in model.checks if c.name == "Approval rate ratio by gender")
    suite = run_suite(SahayakStub(guardrails=True))
    pass_rate = 100 * sum(r.passed for r in suite) / len(suite)
    chain = verify_chain(session)

    def names(items, attr="code", limit=4):
        values = [getattr(i, attr) for i in items]
        return ", ".join(values[:limit]) + (" and more" if len(values) > limit else "")

    return [
        KRI(
            "KRI-01",
            "High and critical risks with no proven-effective control",
            "Assurance",
            pct_unproven,
            f"{pct_unproven:.0f}% ({len(unproven)} of {len(high)})",
            25,
            50,
            owner="Priya Deshmukh",
            note="Residual risk cannot be lowered until a linked control passes an operating test.",
        ),
        KRI(
            "KRI-02",
            "Corrective actions past their due date",
            "Assurance",
            len(overdue_actions),
            str(len(overdue_actions)),
            1,
            3,
            owner="Control owners",
            note=names(overdue_actions) or "None",
        ),
        KRI(
            "KRI-03",
            "Key controls with no operating test",
            "Assurance",
            pct_untested,
            f"{pct_untested:.0f}% ({len(untested)} of {len(key_controls)})",
            20,
            40,
            owner="Priya Deshmukh",
            note=names(untested),
        ),
        KRI(
            "KRI-04",
            "Leavers whose accounts are still active",
            "Cyber",
            len(leavers.exceptions),
            str(len(leavers.exceptions)),
            1,
            1,
            owner="Rahul Kulkarni",
            note=f"From the {EXPORTS_TAKEN_ON:%d %b %Y} HRMS and account exports.",
        ),
        KRI(
            "KRI-05",
            "Privileged accounts without MFA",
            "Cyber",
            len(no_mfa.exceptions),
            str(len(no_mfa.exceptions)),
            1,
            1,
            owner="Kabir Mehta",
            note=no_mfa.summary,
        ),
        KRI(
            "KRI-06",
            "High-risk AI systems without an approved assessment",
            "AI",
            len(unassessed),
            str(len(unassessed)),
            1,
            1,
            owner="Meera Iyer",
            note=names(unassessed, "name") or "None",
        ),
        KRI(
            "KRI-07",
            "Live AI systems with an overdue post-launch review",
            "AI",
            len(overdue_pir),
            str(len(overdue_pir)),
            1,
            2,
            owner="Meera Iyer",
            note=names(overdue_pir, "name") or "None",
        ),
        KRI(
            "KRI-08",
            "CreditLens approval ratio, women to men",
            "AI",
            gender.value,
            f"{gender.value:.2f}",
            0.90,
            0.80,
            higher_is_worse=False,
            owner="Vikram Joshi",
            note=gender.detail,
        ),
        KRI(
            "KRI-09",
            "CreditLens score drift (PSI)",
            "AI",
            model.psi,
            f"{model.psi:.3f}",
            0.10,
            0.25,
            owner="Vikram Joshi",
            note="Validation set vs latest month of production scores.",
        ),
        KRI(
            "KRI-10",
            "Sahayak red-team pass rate, guardrails on",
            "AI",
            pass_rate,
            f"{pass_rate:.0f}%",
            100,
            90,
            higher_is_worse=False,
            owner="Vikram Joshi",
            note=f"{len(suite)} OWASP LLM prompts.",
        ),
        KRI(
            "KRI-11",
            "Audit trail entries that fail verification",
            "Assurance",
            0 if chain.ok else 1,
            "0" if chain.ok else f"Broken at #{chain.broken_at}",
            1,
            1,
            owner="Arjun Rao",
            note=f"{chain.entries} entries in the hash chain.",
        ),
    ]


def rag_counts(kris: list[KRI]) -> dict[str, int]:
    counts = dict.fromkeys(RAG_ORDER, 0)
    for k in kris:
        counts[k.rag] += 1
    return counts


# ---------------------------------------------------------------- headline numbers for the dashboard
def headline(session: Session, today: date | None = None) -> dict:
    today = today or date.today()
    risks = load_risks(session)
    controls = load_controls(session)
    tested = latest_operating_results(session)
    findings = load_findings(session)
    systems = load_ai_systems(session)
    inherent = {r: 0 for r in ("Critical", "High", "Medium", "Low")}
    residual = dict(inherent)
    for r in risks:
        inherent[rating_for(r.inherent_score)] += 1
        res = r.residual_likelihood * r.residual_impact if r.residual_likelihood else r.inherent_score
        residual[rating_for(res)] += 1
    open_findings = [f for f in findings if f.status == "Open"]
    tiers = {}
    for s in systems:
        tiers[s.external_tier] = tiers.get(s.external_tier, 0) + 1
    return {
        "risks": len(risks),
        "inherent": inherent,
        "residual": residual,
        "controls": len(controls),
        "controls_tested": len(tested),
        "controls_effective": sum(1 for t in tested.values() if t.result == "Effective"),
        "tests": len(load_tests(session)),
        "open_findings": len(open_findings),
        "findings_by_severity": {
            s: sum(1 for f in open_findings if f.severity == s) for s in ("High", "Medium", "Low")
        },
        "ai_systems": len(systems),
        "ai_tiers": tiers,
        "ai_live": sum(1 for s in systems if s.lifecycle_stage == "Deployed"),
    }


# ---------------------------------------------------------------- committee pack (PDF)
def _residual_text(risk) -> str:
    if not risk.residual_likelihood:
        return "Not re-rated"
    value = risk.residual_likelihood * risk.residual_impact
    return f"{value} {rating_for(value)}"


def _summary_lines(session: Session, kris: list[KRI], head: dict) -> list[str]:
    reds = [k for k in kris if k.rag == "Red"]
    lines = [
        f"{head['risks']} risks are on the register; {head['inherent']['Critical']} are rated Critical "
        f"before controls and {head['residual']['Critical']} remain Critical after proven controls.",
        f"{head['controls_tested']} of {head['controls']} controls have an operating test; "
        f"{head['controls_effective']} are effective. {head['open_findings']} findings are open.",
        f"{len(reds)} of {len(kris)} key risk indicators are red: " + "; ".join(k.name for k in reds) + "."
        if reds
        else "No key risk indicator is red.",
        f"{head['ai_systems']} AI systems are inventoried ({head['ai_live']} live). CreditLens fails the "
        "internal fairness appetite but meets the four-fifths floor; Sahayak is not cleared for go-live.",
    ]
    return lines


def _decisions(kris: list[KRI]) -> list[str]:
    by_code = {k.code: k for k in kris}
    asks = []
    if by_code["KRI-04"].rag == "Red":
        asks.append(
            "Direct IT Operations to disable leaver accounts within 24 hours and confirm by the next meeting."
        )
    if by_code["KRI-05"].rag == "Red":
        asks.append("Approve enforcing MFA on every privileged account, with no service-account exceptions.")
    if by_code["KRI-08"].rag != "Green":
        asks.append(
            "Decide whether CreditLens may continue while the gender fairness gap is remediated, "
            "or should move to full manual review for affected segments."
        )
    if by_code["KRI-06"].rag == "Red":
        asks.append(
            "Note that high-risk AI systems without an approved assessment stay blocked from go-live."
        )
    if by_code["KRI-07"].rag != "Green":
        asks.append("Require the overdue post-launch reviews to be completed within 30 days.")
    return asks or ["No decisions requested this cycle."]


def committee_pack_pdf(session: Session, today: date | None = None) -> bytes:
    """A short board risk committee pack: summary, KRIs, top risks, findings, AI portfolio, decisions."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    today = today or date.today()
    kris = compute_kris(session, today)
    head = headline(session, today)
    ink, marigold = colors.HexColor("#14213D"), colors.HexColor("#E8A33D")
    rag_fill = {"Red": "#F6DDE0", "Amber": "#FBEBD2", "Green": "#DCEFEA"}
    rag_ink = {"Red": "#8E2433", "Amber": "#8A5A12", "Green": "#17605A"}

    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13)
    small = ParagraphStyle(
        "small", parent=body, fontSize=8, leading=10.5, textColor=colors.HexColor("#4A5568")
    )
    cell = ParagraphStyle("cell", parent=body, fontSize=8, leading=10, alignment=TA_LEFT)
    h1 = ParagraphStyle("h1", parent=body, fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=ink)
    h2 = ParagraphStyle(
        "h2",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=ink,
        spaceBefore=10,
        spaceAfter=6,
    )

    def table(rows, widths, rag_col=None):
        """Header row in ink; optional RAG column shaded red, amber or green."""
        data = [[Paragraph(f'<font color="white"><b>{v}</b></font>', cell) for v in rows[0]]]
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), ink),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5DBE5")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for i, row in enumerate(rows[1:], start=1):
            line = [Paragraph(str(v), cell) for v in row]
            if rag_col is not None and row[rag_col] in rag_fill:
                rag = row[rag_col]
                line[rag_col] = Paragraph(f'<font color="{rag_ink[rag]}"><b>{rag}</b></font>', cell)
                style.append(("BACKGROUND", (rag_col, i), (rag_col, i), colors.HexColor(rag_fill[rag])))
            data.append(line)
        t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
        t.setStyle(TableStyle(style))
        return t

    story = [
        Paragraph(f"{COMPANY}", small),
        Spacer(1, 4 * mm),
        Paragraph("Risk &amp; AI Governance Committee pack", h1),
        Paragraph(f"{today:%B %Y} &middot; prepared with {APP_NAME} &middot; synthetic data", small),
        Spacer(1, 6 * mm),
        Paragraph("1. Executive summary", h2),
        *[Paragraph(f"&bull; {line}", body) for line in _summary_lines(session, kris, head)],
        Paragraph("2. Key risk indicators", h2),
        table(
            [["KRI", "Indicator", "Value", "Status", "Threshold", "Owner"]]
            + [
                [k.code, k.name, k.display, k.rag, k.threshold, k.owner]
                for k in sorted(kris, key=lambda k: (RAG_ORDER[k.rag], k.code))
            ],
            [16, 62, 24, 16, 38, 26],
            rag_col=3,
        ),
        Paragraph("3. Decisions requested", h2),
        *[Paragraph(f"{i}. {ask}", body) for i, ask in enumerate(_decisions(kris), start=1)],
        PageBreak(),
        Paragraph("4. Top ten risks by inherent score", h2),
        table(
            [["Risk", "Title", "Owner", "Inherent", "Residual", "Treatment"]]
            + [
                [
                    r.code,
                    r.title,
                    r.owner.full_name,
                    f"{r.inherent_score} {rating_for(r.inherent_score)}",
                    _residual_text(r),
                    r.treatment,
                ]
                for r in sorted(load_risks(session), key=lambda r: (-r.inherent_score, r.code))[:10]
            ],
            [16, 70, 28, 20, 18, 22],
        ),
        Paragraph("5. Open audit findings", h2),
        table(
            [["Finding", "Issue", "Severity", "Control owner", "Actions done"]]
            + [
                [
                    f.code,
                    f.title,
                    f.severity,
                    f.control.owner.full_name,
                    f"{sum(a.status == 'Done' for a in f.actions)} of {len(f.actions)}",
                ]
                for f in load_findings(session)
                if f.status == "Open"
            ],
            [18, 86, 18, 30, 22],
        ),
        Paragraph("6. AI portfolio", h2),
    ]
    assessments = load_assessments(session)
    ai_rows = [["System", "Tier", "Stage", "Assessment", "Post-launch review"]]
    for s in load_ai_systems(session):
        last = latest_assessment(assessments, s)
        due = next_review_due(s, reviews_for(session, s))
        ai_rows.append(
            [
                s.name,
                f"{s.external_tier}, tier {s.internal_tier}",
                s.lifecycle_stage,
                last.status if last else "Not assessed",
                f"{review_status(due, today)}" + (f", due {due:%d %b %Y}" if due else ""),
            ]
        )
    validations = load_validations(session)
    story += [
        table(ai_rows, [28, 40, 22, 30, 54]),
        Spacer(1, 3 * mm),
        Paragraph(
            "Latest model validation: "
            + (
                f"{validations[0].code} on {validations[0].run_on:%d %b %Y}, {validations[0].result}."
                if validations
                else "none recorded; metrics in this pack are computed live from the hold-out set."
            ),
            body,
        ),
        Spacer(1, 8 * mm),
        Paragraph(DISCLAIMER, small),
    ]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(marigold)
        canvas.rect(0, A4[1] - 4 * mm, A4[0], 4 * mm, stroke=0, fill=1)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#4A5568"))
        canvas.drawString(
            15 * mm, 10 * mm, f"{APP_NAME} committee pack, {today:%d %b %Y}. Synthetic data only."
        )
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title="Risk and AI Governance Committee pack",
        author=APP_NAME,
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


# ---------------------------------------------------------------- audit evidence pack (ZIP)
def _csv(rows: list[dict]) -> bytes:
    if not rows:
        return b"No records.\n"
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def audit_pack_zip(session: Session, today: date | None = None) -> tuple[bytes, list[dict]]:
    """Everything an auditor asks for, with a SHA-256 manifest. Returns (zip bytes, manifest rows)."""
    today = today or date.today()
    files: dict[str, bytes] = {}
    files["01-risk-register.csv"] = _csv(risk_rows(load_risks(session)))
    files["02-risk-control-matrix.xlsx"] = rcm_workbook(session)
    files["03-control-tests.csv"] = _csv(
        [
            {
                "test": t.code,
                "control": t.control.code,
                "type": t.test_type,
                "method": t.method,
                "period": t.period,
                "sample": t.sample_size,
                "exceptions": t.exceptions,
                "result": t.result,
                "tester": t.tester.username,
                "reviewer": t.reviewer.username if t.reviewer else "",
                "performed_on": t.performed_on.isoformat(),
                "evidence": "; ".join(e.code for e in t.evidence),
            }
            for t in load_tests(session)
        ]
    )
    findings = load_findings(session)
    files["04-findings-and-actions.csv"] = _csv(
        [
            {
                "finding": f.code,
                "control": f.control.code,
                "title": f.title,
                "severity": f.severity,
                "status": f.status,
                "raised_on": f.raised_on.isoformat(),
                "action": a.code if a else "",
                "action_owner": a.owner.username if a else "",
                "due": a.due_date.isoformat() if a else "",
                "action_status": a.status if a else "",
            }
            for f in findings
            for a in (f.actions or [None])
        ]
    )
    evidence_rows = []
    for t in load_tests(session):
        for e in t.evidence:
            path = evidence_dir() / e.stored_name
            data = path.read_bytes() if path.exists() else b""
            intact = bool(data) and hashlib.sha256(data).hexdigest() == e.sha256
            if data:
                files[f"05-evidence/{e.code}-{e.filename}"] = data
            evidence_rows.append(
                {
                    "evidence": e.code,
                    "test": t.code,
                    "file": e.filename,
                    "sha256_at_upload": e.sha256,
                    "intact": "Yes" if intact else "NO",
                }
            )
    files["05-evidence-register.csv"] = _csv(evidence_rows)
    assessments = load_assessments(session)
    files["06-ai-inventory.csv"] = _csv(
        [
            {
                "code": s.code,
                "name": s.name,
                "purpose": s.purpose,
                "owner": s.owner.username,
                "tier": s.external_tier,
                "internal_tier": s.internal_tier,
                "stage": s.lifecycle_stage,
                "tier_reasons": s.tier_reasons,
                "latest_assessment": (
                    latest_assessment(assessments, s).status
                    if latest_assessment(assessments, s)
                    else "Not assessed"
                ),
            }
            for s in load_ai_systems(session)
        ]
    )
    files["07-ai-assessments.csv"] = _csv(
        [
            {
                "assessment": a.code,
                "system": a.ai_system.name,
                "assessor": a.assessor.username,
                "status": a.status,
                "approver": a.approver.username if a.approver else "",
                "answers": a.answers_json,
            }
            for a in assessments
        ]
    )
    files["08-model-validations.csv"] = _csv(
        [
            {
                "run": v.code,
                "model": v.ai_system.name,
                "validator": v.validator.username,
                "date": v.run_on.isoformat(),
                "result": v.result,
                "control_tests": v.test_codes,
                "metrics": v.metrics_json,
            }
            for v in load_validations(session)
        ]
    )
    files["09-kris.csv"] = _csv(
        [
            {
                "kri": k.code,
                "indicator": k.name,
                "value": k.display,
                "status": k.rag,
                "threshold": k.threshold,
                "owner": k.owner,
            }
            for k in compute_kris(session, today)
        ]
    )
    chain = verify_chain(session)
    files["10-audit-trail.csv"] = audit_csv(session)
    files["10-audit-trail-verification.json"] = json.dumps(
        {
            "entries": chain.entries,
            "chain_intact": chain.ok,
            "broken_at": chain.broken_at,
            "checked_on": today.isoformat(),
        },
        indent=2,
    ).encode()

    manifest = [
        {"file": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in sorted(files.items())
    ]
    intact_count = sum(r["intact"] == "Yes" for r in evidence_rows)
    chain_text = "yes" if chain.ok else f"NO, broken at entry {chain.broken_at}"
    readme = (
        f"{APP_NAME} audit evidence pack\n{COMPANY}\nGenerated {today:%d %b %Y}\n\n"
        "Every file in this pack is listed in MANIFEST.csv with its SHA-256 hash, so the pack can be checked "
        "for completeness and alteration after it is handed over.\n"
        f"Evidence files intact: {intact_count} of {len(evidence_rows)}.\n"
        f"Audit trail chain intact: {chain_text}.\n\n"
        f"{DISCLAIMER}\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", readme)
        archive.writestr("MANIFEST.csv", _csv(manifest))
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    return buffer.getvalue(), manifest
