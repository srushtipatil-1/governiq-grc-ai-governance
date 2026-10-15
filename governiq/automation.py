"""Continuous control monitoring: automated tests that read system exports and record their own results.

An automated check tests the WHOLE population (every leaver, every privileged account), not a sample.
Each run is saved as an ordinary operating test through record_test(), so the same rules apply:
it needs evidence (the exceptions file is generated and hashed), it opens findings on failure and it
can close findings when it passes. The exports in data/seed/systems/ are synthetic.
"""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from governiq.assurance import NewTest, RecordedTest, record_test
from governiq.config import DATA_DIR

SYSTEMS_DIR = DATA_DIR / "seed" / "systems"
EXPORTS_TAKEN_ON = date(2026, 10, 14)  # the synthetic exports were "taken" on this date


def _read(name: str, folder: Path) -> list[dict]:
    with open(folder / name, encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


@dataclass
class CheckResult:
    population: int
    exceptions: list[dict]
    summary: str


# ---------------------------------------------------------------- the five checks
def leavers_with_active_accounts(folder: Path, as_of: date) -> CheckResult:
    leavers = {r["employee_id"]: r for r in _read("hrms_leavers.csv", folder)}
    accounts = _read("system_accounts.csv", folder)
    exceptions = []
    for account in accounts:
        leaver = leavers.get(account["employee_id"])
        if leaver and account["status"] == "active":
            days = (as_of - date.fromisoformat(leaver["exit_date"])).days
            if days > 1:
                exceptions.append({**account, "exit_date": leaver["exit_date"], "days_since_exit": days})
    summary = (
        f"{len(leavers)} leavers checked against {len(accounts)} accounts; {len(exceptions)} still active."
    )
    return CheckResult(len(leavers), exceptions, summary)


def privileged_accounts_without_mfa(folder: Path, as_of: date) -> CheckResult:
    privileged = [
        a
        for a in _read("system_accounts.csv", folder)
        if a["privileged"] == "yes" and a["status"] == "active"
    ]
    exceptions = [a for a in privileged if a["mfa_enabled"] != "yes"]
    summary = f"{len(privileged)} active privileged accounts; {len(exceptions)} without MFA."
    return CheckResult(len(privileged), exceptions, summary)


def failed_backups(folder: Path, as_of: date) -> CheckResult:
    recent = [
        j
        for j in _read("backup_jobs.csv", folder)
        if date.fromisoformat(j["job_date"]) >= as_of - timedelta(30)
    ]
    exceptions = [j for j in recent if j["status"] != "success"]
    summary = f"{len(recent)} backup jobs in the last 30 days; {len(exceptions)} failed."
    return CheckResult(len(recent), exceptions, summary)


def late_critical_patches(folder: Path, as_of: date) -> CheckResult:
    critical = [p for p in _read("patch_status.csv", folder) if p["severity"] == "Critical"]
    exceptions = []
    for patch in critical:
        released = date.fromisoformat(patch["released_on"])
        installed = date.fromisoformat(patch["installed_on"]) if patch["installed_on"] else None
        days = ((installed or as_of) - released).days
        if days > 14:
            exceptions.append({**patch, "days_open": days})
    summary = f"{len(critical)} critical patch installations checked; {len(exceptions)} took over 14 days."
    return CheckResult(len(critical), exceptions, summary)


def stale_privileged_reviews(folder: Path, as_of: date) -> CheckResult:
    privileged = [
        a
        for a in _read("system_accounts.csv", folder)
        if a["privileged"] == "yes" and a["status"] == "active"
    ]
    exceptions = [a for a in privileged if (as_of - date.fromisoformat(a["last_access_review"])).days > 31]
    summary = (
        f"{len(privileged)} active privileged accounts; {len(exceptions)} not reviewed in the last month."
    )
    return CheckResult(len(privileged), exceptions, summary)


@dataclass
class AutomatedCheck:
    code: str
    name: str
    control_code: str
    source: str
    run: Callable[[Path, date], CheckResult]


CHECKS = [
    AutomatedCheck(
        "CCM-01",
        "Leavers with active accounts",
        "CTL-IAM-02",
        "HRMS leavers vs system accounts",
        leavers_with_active_accounts,
    ),
    AutomatedCheck(
        "CCM-02",
        "Privileged accounts without MFA",
        "CTL-IAM-04",
        "System accounts",
        privileged_accounts_without_mfa,
    ),
    AutomatedCheck("CCM-03", "Failed backups, last 30 days", "CTL-OPS-01", "Backup job log", failed_backups),
    AutomatedCheck(
        "CCM-04",
        "Critical patches older than 14 days",
        "CTL-OPS-02",
        "Patch status export",
        late_critical_patches,
    ),
    AutomatedCheck(
        "CCM-05",
        "Privileged accounts not reviewed monthly",
        "CTL-IAM-05",
        "System accounts",
        stale_privileged_reviews,
    ),
]
CHECKS_BY_CODE = {check.code: check for check in CHECKS}


def _as_csv(rows: list[dict], summary: str) -> bytes:
    buffer = io.StringIO()
    buffer.write(f"# {summary}\n")
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    else:
        buffer.write("No exceptions found.\n")
    return buffer.getvalue().encode("utf-8")


def run_check(
    session: Session,
    code: str,
    actor: str,
    folder: Path = SYSTEMS_DIR,
    as_of: date = EXPORTS_TAKEN_ON,
    performed_on: date | None = None,
) -> tuple[CheckResult, RecordedTest]:
    """Run one automated check and record it as an operating test with its results as evidence."""
    check = CHECKS_BY_CODE[code]
    result = check.run(folder, as_of)
    performed_on = performed_on or date.today()
    evidence = (
        f"{check.code}-{performed_on.isoformat()}-results.csv",
        _as_csv(result.exceptions, result.summary),
    )
    recorded = record_test(
        session,
        NewTest(
            control_code=check.control_code,
            test_type="Operating",
            method="Automated",
            period=f"Exports of {as_of.isoformat()}",
            sample_size=max(result.population, 1),
            exceptions=len(result.exceptions),
            performed_on=performed_on,
            notes=f"{check.code} {check.name}: full population tested. {result.summary}",
        ),
        actor=actor,
        evidence_files=[evidence],
    )
    return result, recorded
