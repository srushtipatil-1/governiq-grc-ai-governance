"""Audit trail: verify the hash chain and export the log."""

import csv
import io
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from governiq.models import GENESIS_HASH, AuditLog, audit_entry_hash


@dataclass
class ChainReport:
    entries: int
    ok: bool
    broken_at: int | None = None  # id of the first entry that does not verify
    reason: str = ""


def verify_chain(session: Session) -> ChainReport:
    """Recompute every hash in order. Any edited, inserted or deleted entry shows up as a break."""
    previous = GENESIS_HASH
    entries = session.scalars(select(AuditLog).order_by(AuditLog.id)).all()
    for entry in entries:
        if entry.prev_hash != previous:
            return ChainReport(
                len(entries),
                False,
                entry.id,
                "does not point to the entry before it (one was deleted or inserted)",
            )
        if audit_entry_hash(entry) != entry.entry_hash:
            return ChainReport(
                len(entries), False, entry.id, "its contents no longer match its hash (it was edited)"
            )
        previous = entry.entry_hash
    return ChainReport(len(entries), True)


def load_audit(session: Session, limit: int | None = None) -> list[AuditLog]:
    query = select(AuditLog).order_by(AuditLog.id.desc())
    if limit:
        query = query.limit(limit)
    return list(session.scalars(query))


def audit_csv(session: Session) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "timestamp_utc", "user", "action", "entity", "entity_id", "before", "after",
                     "prev_hash", "entry_hash"])  # fmt: skip
    for e in reversed(load_audit(session)):
        when = e.ts.isoformat(timespec="seconds")
        writer.writerow([e.id, when, e.username, e.action, e.entity, e.entity_id, e.before_json or "",
                         e.after_json or "", e.prev_hash, e.entry_hash])  # fmt: skip
    return buffer.getvalue().encode("utf-8")
