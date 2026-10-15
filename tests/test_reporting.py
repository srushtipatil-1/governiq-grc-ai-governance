"""Phase 12 tests: KRIs and their thresholds, headline numbers, the committee PDF and the audit pack."""

import csv
import hashlib
import io
import zipfile
from datetime import date

import pytest
from sqlalchemy import select, text

from governiq.assurance import evidence_dir
from governiq.models import Action, Evidence
from governiq.reporting import KRI, audit_pack_zip, committee_pack_pdf, compute_kris, headline, rag_counts

TODAY = date(2026, 10, 15)


@pytest.mark.parametrize(
    ("value", "higher_is_worse", "rag"),
    [(0, True, "Green"), (1, True, "Amber"), (3, True, "Red"),
     (0.95, False, "Green"), (0.85, False, "Amber"), (0.70, False, "Red")],
)  # fmt: skip
def test_rag_thresholds_work_in_both_directions(value, higher_is_worse, rag):
    amber, red = (1, 3) if higher_is_worse else (0.90, 0.80)
    assert KRI("K", "k", "AI", value, str(value), amber, red, higher_is_worse).rag == rag


def test_zero_tolerance_threshold_reads_simply():
    assert KRI("K", "k", "Cyber", 0, "0", 1, 1).threshold == "Red >= 1"


def test_seeded_kris(session):
    kris = {k.code: k for k in compute_kris(session, TODAY)}
    assert len(kris) == 11
    reds = {code for code, k in kris.items() if k.rag == "Red"}
    assert reds == {"KRI-01", "KRI-03", "KRI-04", "KRI-05", "KRI-06"}
    assert kris["KRI-06"].note == "TalentSift"
    assert kris["KRI-07"].note == "FraudShield"
    assert kris["KRI-08"].display == "0.85" and kris["KRI-08"].rag == "Amber"
    assert kris["KRI-10"].rag == "Green" and kris["KRI-11"].rag == "Green"
    assert rag_counts(list(kris.values())) == {"Red": 5, "Amber": 3, "Green": 3}


def test_overdue_actions_turn_kri_02_red(session):
    assert next(k for k in compute_kris(session, TODAY) if k.code == "KRI-02").rag == "Green"
    later = date(2026, 12, 20)  # ACT-001, ACT-003 and ACT-004 are all past due by then
    kri = next(k for k in compute_kris(session, later) if k.code == "KRI-02")
    assert (kri.value, kri.rag) == (3, "Red")


def test_completed_actions_are_not_overdue(session):
    for action in session.scalars(select(Action)):
        action.status = "Done"
    session.commit()
    kri = next(k for k in compute_kris(session, date(2027, 1, 1)) if k.code == "KRI-02")
    assert kri.rag == "Green"


def test_tampering_turns_audit_kri_red(session):
    session.execute(text("UPDATE audit_log SET action = 'x' WHERE id = 2"))
    session.commit()
    kri = next(k for k in compute_kris(session, TODAY) if k.code == "KRI-11")
    assert kri.rag == "Red" and kri.display == "Broken at #2"


def test_headline_numbers(session):
    head = headline(session, TODAY)
    assert head["risks"] == 30 and head["inherent"]["Critical"] == 1 and head["residual"]["Critical"] == 0
    assert (head["controls_tested"], head["controls_effective"], head["open_findings"]) == (9, 6, 4)
    assert head["ai_tiers"] == {"High risk": 2, "Minimal risk": 1, "Limited risk": 1}


def test_committee_pack_is_a_two_page_pdf(session):
    pdf = committee_pack_pdf(session, TODAY)
    assert pdf.startswith(b"%PDF")
    assert b"/Count 2" in pdf


def test_audit_pack_manifest_matches_every_file(session):
    data, manifest = audit_pack_zip(session, TODAY)
    archive = zipfile.ZipFile(io.BytesIO(data))
    names = set(archive.namelist())
    assert {"README.txt", "MANIFEST.csv", "02-risk-control-matrix.xlsx", "10-audit-trail.csv"} <= names
    listed = list(csv.DictReader(io.StringIO(archive.read("MANIFEST.csv").decode())))
    assert len(listed) == len(manifest) == len(names) - 2
    for row in listed:
        assert hashlib.sha256(archive.read(row["file"])).hexdigest() == row["sha256"]
    assert sum(1 for n in names if n.startswith("05-evidence/")) == 11
    assert "Evidence files intact: 11 of 11" in archive.read("README.txt").decode()


def test_audit_pack_flags_altered_evidence(session):
    evidence = session.scalar(select(Evidence).where(Evidence.code == "EV-0001"))
    (evidence_dir() / evidence.stored_name).write_bytes(b"altered after upload")
    data, _ = audit_pack_zip(session, TODAY)
    archive = zipfile.ZipFile(io.BytesIO(data))
    register = archive.read("05-evidence-register.csv").decode()
    assert "EV-0001" in register and ",NO" in register
    assert "Evidence files intact: 10 of 11" in archive.read("README.txt").decode()
