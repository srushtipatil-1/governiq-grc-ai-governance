"""Phase 11 tests: password hashing, sign-in and lockout, permissions, and the tamper-evident audit trail."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, text

from governiq.audit import audit_csv, verify_chain
from governiq.auth import (
    DEMO_PASSWORD,
    GENERIC_LOGIN_ERROR,
    authenticate,
    can,
    hash_password,
    password_errors,
    set_password,
    unlock_user,
    verify_password,
)
from governiq.models import AuditLog, User

NOW = datetime(2026, 10, 15, 9, 0)


# ---------------------------------------------------------------- hashing
def test_hash_is_salted_and_verifies():
    first, second = hash_password("correct horse 42"), hash_password("correct horse 42")
    assert first != second  # random salt: same password, different hash
    assert first.startswith("scrypt$") and "correct horse" not in first
    assert verify_password("correct horse 42", first)
    assert not verify_password("correct horse 43", first)


@pytest.mark.parametrize("stored", [None, "", "md5$abc", "scrypt$broken"])
def test_malformed_hashes_never_verify(stored):
    assert not verify_password("anything", stored)


@pytest.mark.parametrize(
    ("password", "problem"),
    [("short1", "12 characters"), ("onlyletterslong", "letters and numbers"), ("password1234", "common")],
)
def test_password_policy(password, problem):
    assert any(problem in e for e in password_errors(password))


def test_seeded_users_have_unique_hashes_of_the_demo_password(session):
    hashes = session.scalars(select(User.password_hash)).all()
    assert len(set(hashes)) == len(hashes) == 9
    assert all(verify_password(DEMO_PASSWORD, h) for h in hashes)


# ---------------------------------------------------------------- sign-in
def test_successful_sign_in_is_logged(session):
    user = authenticate(session, "Priya.Analyst ", DEMO_PASSWORD, now=NOW)
    assert (user.username, user.last_login) == ("priya.analyst", NOW)
    assert session.scalar(select(AuditLog).order_by(AuditLog.id.desc())).action == "login"


def test_unknown_user_and_wrong_password_get_the_same_message(session):
    for username, password in (("nobody", DEMO_PASSWORD), ("priya.analyst", "wrong-password-1")):
        with pytest.raises(ValueError) as problem:
            authenticate(session, username, password, now=NOW)
        assert str(problem.value) == GENERIC_LOGIN_ERROR


def test_five_wrong_passwords_lock_the_account_for_fifteen_minutes(session):
    for _ in range(5):
        with pytest.raises(ValueError):
            authenticate(session, "priya.analyst", "wrong-password-1", now=NOW)
    with pytest.raises(ValueError, match="locked"):
        authenticate(session, "priya.analyst", DEMO_PASSWORD, now=NOW + timedelta(minutes=5))
    assert authenticate(session, "priya.analyst", DEMO_PASSWORD, now=NOW + timedelta(minutes=16))
    actions = session.scalars(select(AuditLog.action).where(AuditLog.entity == "session")).all()
    assert actions.count("login_failed") == 4 and actions.count("account_locked") == 1


def test_inactive_user_cannot_sign_in(session):
    session.scalar(select(User).where(User.username == "neha.hr")).is_active = False
    session.commit()
    with pytest.raises(ValueError, match="Wrong username"):
        authenticate(session, "neha.hr", DEMO_PASSWORD)


def test_admin_resets_password_and_unlocks(session):
    set_password(session, "neha.hr", "new-strong-pass-77", "admin.demo")
    assert authenticate(session, "neha.hr", "new-strong-pass-77")
    session.scalar(select(User).where(User.username == "neha.hr")).locked_until = NOW + timedelta(days=1)
    session.commit()
    unlock_user(session, "neha.hr", "admin.demo")
    assert session.scalar(select(User).where(User.username == "neha.hr")).locked_until is None


@pytest.mark.parametrize(
    ("call", "message"),
    [(lambda s: set_password(s, "neha.hr", "new-strong-pass-77", "priya.analyst"), "Only an admin"),
     (lambda s: set_password(s, "neha.hr", "weak", "admin.demo"), "12 characters"),
     (lambda s: unlock_user(s, "neha.hr", "arjun.audit"), "Only an admin")],
    ids=["analyst-resets-other", "weak-password", "auditor-unlocks"],
)  # fmt: skip
def test_account_admin_rules(session, call, message):
    with pytest.raises(ValueError, match=message):
        call(session)


def test_users_can_change_their_own_password(session):
    set_password(session, "priya.analyst", "my-own-pass-2026", "priya.analyst")
    assert authenticate(session, "priya.analyst", "my-own-pass-2026")


# ---------------------------------------------------------------- permissions
@pytest.mark.parametrize(
    ("role", "permission", "allowed"),
    [("Admin", "manage_users", True), ("Admin", "record_test", False),
     ("Auditor", "verify_audit_trail", True), ("Auditor", "add_risk", False),
     ("AI Governance Lead", "approve_go_live", True),
     ("GRC Analyst", "approve_go_live", False), ("Control Owner", "verify_audit_trail", False)],
)  # fmt: skip
def test_permission_matrix(role, permission, allowed):
    assert can(role, permission) is allowed


# ---------------------------------------------------------------- audit trail
def test_seeded_audit_trail_verifies(session):
    report = verify_chain(session)
    assert report.ok and report.entries > 20


def test_editing_an_entry_is_detected(session):
    session.execute(text("UPDATE audit_log SET username = 'someone.else' WHERE id = 3"))
    session.commit()
    report = verify_chain(session)
    assert (report.ok, report.broken_at) == (False, 3)
    assert "edited" in report.reason


def test_deleting_an_entry_is_detected(session):
    session.execute(text("DELETE FROM audit_log WHERE id = 4"))
    session.commit()
    report = verify_chain(session)
    assert (report.ok, report.broken_at) == (False, 5)
    assert "deleted or inserted" in report.reason


def test_new_entries_extend_the_chain(session):
    before = verify_chain(session).entries
    authenticate(session, "meera.aigov", DEMO_PASSWORD)
    report = verify_chain(session)
    assert report.ok and report.entries == before + 1


def test_audit_export_contains_hashes(session):
    rows = audit_csv(session).decode().splitlines()
    assert rows[0].endswith("prev_hash,entry_hash")
    assert rows[1].split(",")[-2] == "0" * 64  # the first entry points at the genesis hash
