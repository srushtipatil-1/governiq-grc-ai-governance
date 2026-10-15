"""Sign-in and permissions: scrypt password hashes, account lockout and a role-based permission matrix.

Demo note: every seeded account shares one published demo password so recruiters can try each role.
It protects nothing real (all data is synthetic). Set GOVERNIQ_DEMO_MODE=false to hide the demo sign-in
buttons, and give each user their own password.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from governiq.models import AuditLog, User

DEMO_PASSWORD = os.environ.get("GOVERNIQ_DEMO_PASSWORD", "governiq-demo-2026")
MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=15)
GENERIC_LOGIN_ERROR = "Wrong username or password."  # same message either way, so usernames can't be probed


def demo_mode() -> bool:
    return os.environ.get("GOVERNIQ_DEMO_MODE", "true").lower() != "false"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------- password hashing (scrypt, stdlib)
def hash_password(password: str) -> str:
    n = int(os.environ.get("GOVERNIQ_SCRYPT_N", 2**14))  # tests lower this to stay fast
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=8, p=1, dklen=32)
    return f"scrypt${n}$8$1${base64.b64encode(salt).decode()}${base64.b64encode(key).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    try:
        scheme, n, r, p, salt, key = (stored or "").split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    candidate = hashlib.scrypt(
        password.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32
    )
    return hmac.compare_digest(candidate, base64.b64decode(key))


def password_errors(password: str) -> list[str]:
    errors = []
    if len(password) < 12:
        errors.append("at least 12 characters")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        errors.append("letters and numbers")
    if password.lower() in ("password1234", "governiq1234", "qwerty123456"):
        errors.append("not a common password")
    return errors


# ---------------------------------------------------------------- sign-in
def _log(session: Session, username: str, action: str, after: dict | None = None) -> None:
    session.add(
        AuditLog(username=username, action=action, entity="session", entity_id=username,
                 after_json=json.dumps(after) if after else None)
    )  # fmt: skip


def authenticate(session: Session, username: str, password: str, now: datetime | None = None) -> User:
    """Return the user, or raise ValueError. Five wrong passwords lock the account for 15 minutes."""
    now = now or _now()
    user = session.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None or not user.is_active:
        _log(session, username.strip()[:50] or "(blank)", "login_failed", {"reason": "unknown or inactive"})
        session.commit()
        raise ValueError(GENERIC_LOGIN_ERROR)
    if user.locked_until and user.locked_until > now:
        minutes = int((user.locked_until - now).total_seconds() // 60) + 1
        raise ValueError(f"This account is locked after too many attempts. Try again in {minutes} minutes.")
    if not verify_password(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.locked_until, user.failed_logins = now + LOCKOUT, 0
            _log(session, user.username, "account_locked", {"minutes": int(LOCKOUT.total_seconds() // 60)})
        else:
            _log(session, user.username, "login_failed", {"attempt": user.failed_logins})
        session.commit()
        raise ValueError(GENERIC_LOGIN_ERROR)
    user.failed_logins, user.locked_until, user.last_login = 0, None, now
    _log(session, user.username, "login")
    session.commit()
    return user


def demo_sign_in(session: Session, username: str) -> User:
    """One-click demo sign-in. Only in demo mode, and it skips the lockout on purpose, so a visitor who
    types wrong passwords cannot lock everyone else out of the public demo. Logged as 'demo_login'."""
    if not demo_mode():
        raise ValueError("Demo sign-in is switched off.")
    user = session.scalar(select(User).where(User.username == username, User.is_active))
    if user is None:
        raise ValueError(GENERIC_LOGIN_ERROR)
    user.last_login = _now()
    _log(session, user.username, "demo_login")
    session.commit()
    return user


def record_logout(session: Session, username: str) -> None:
    _log(session, username, "logout")
    session.commit()


def set_password(session: Session, username: str, new_password: str, actor: str) -> None:
    acting = session.scalar(select(User).where(User.username == actor))
    user = session.scalar(select(User).where(User.username == username))
    if user is None:
        raise ValueError(f"User '{username}' does not exist.")
    if acting is None or (acting.id != user.id and not can(acting.role, "manage_users")):
        raise ValueError("Only an admin can reset another person's password.")
    errors = password_errors(new_password)
    if errors:
        raise ValueError("Password needs " + ", ".join(errors) + ".")
    user.password_hash, user.failed_logins, user.locked_until = hash_password(new_password), 0, None
    session.add(AuditLog(username=actor, action="password_set", entity="user", entity_id=username))
    session.commit()


def unlock_user(session: Session, username: str, actor: str) -> None:
    acting = session.scalar(select(User).where(User.username == actor))
    if acting is None or not can(acting.role, "manage_users"):
        raise ValueError("Only an admin can unlock accounts.")
    user = session.scalar(select(User).where(User.username == username))
    if user is None:
        raise ValueError(f"User '{username}' does not exist.")
    user.locked_until, user.failed_logins = None, 0
    session.add(AuditLog(username=actor, action="unlock", entity="user", entity_id=username))
    session.commit()


# ---------------------------------------------------------------- permissions (role-based access control)
PERMISSIONS = {
    "view_all": ("Admin", "GRC Analyst", "Control Owner", "AI Governance Lead", "Auditor"),
    "add_risk": ("GRC Analyst", "AI Governance Lead"),
    "record_test": ("GRC Analyst", "AI Governance Lead"),
    "run_automated_checks": ("GRC Analyst", "AI Governance Lead"),
    "complete_own_action": ("Control Owner", "GRC Analyst", "AI Governance Lead"),
    "register_ai_system": ("GRC Analyst", "AI Governance Lead"),
    "assess_ai_system": ("GRC Analyst", "AI Governance Lead"),
    "approve_ai_assessment": ("AI Governance Lead",),
    "approve_go_live": ("AI Governance Lead",),
    "edit_own_model_card": ("Control Owner", "GRC Analyst", "AI Governance Lead"),
    "validate_model": ("GRC Analyst", "AI Governance Lead"),
    "verify_audit_trail": ("Admin", "Auditor", "GRC Analyst", "AI Governance Lead"),
    "manage_users": ("Admin",),
}
PERMISSION_LABELS = {
    "view_all": "View every module",
    "add_risk": "Add risks",
    "record_test": "Record control tests",
    "run_automated_checks": "Run automated control checks",
    "complete_own_action": "Complete own corrective actions",
    "register_ai_system": "Register AI systems",
    "assess_ai_system": "Assess AI systems",
    "approve_ai_assessment": "Approve AI assessments",
    "approve_go_live": "Approve AI go-live",
    "edit_own_model_card": "Edit model cards of own systems",
    "validate_model": "Validate models",
    "verify_audit_trail": "Verify and export the audit trail",
    "manage_users": "Manage users and passwords",
}


def can(role: str, permission: str) -> bool:
    return role in PERMISSIONS.get(permission, ())
