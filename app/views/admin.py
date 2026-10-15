"""Audit trail and users: verify the hash chain, export the log, manage accounts and see who can do what."""

import pandas as pd
import streamlit as st
from sqlalchemy import select

from governiq.audit import audit_csv, load_audit, verify_chain
from governiq.auth import PERMISSION_LABELS, PERMISSIONS, can, demo_mode, set_password, unlock_user
from governiq.demo import rebuild_demo_data
from governiq.models import ROLES, AuditLog, User
from governiq.ui import current_actor, demo_engine, get_session

session = get_session()
actor = session.scalar(select(User).where(User.username == current_actor()))
report = verify_chain(session)
users = session.scalars(select(User).order_by(User.role, User.username)).all()

st.html(
    f"""
    <div class="giq-page-head">
      <h1>Audit trail and users</h1>
      <p>{report.entries:,} audit entries. Each one stores the SHA-256 hash of the entry before it, so
      editing, deleting or inserting any past entry breaks the chain from that point on.
      {len(users)} user accounts, passwords stored as salted scrypt hashes, never in plain text.</p>
    </div>
    """
)

if "admin_flash" in st.session_state:
    kind, message = st.session_state.pop("admin_flash")
    (st.success if kind == "ok" else st.warning)(message, icon=":material/info:")

trail_tab, users_tab, perms_tab = st.tabs(["Audit trail", "Users", "Permissions"])

# ---------- Audit trail ----------
with trail_tab:
    if report.ok:
        st.success(
            f"Chain verified: all {report.entries:,} entries match their hashes.", icon=":material/verified:"
        )
    else:
        st.error(f"Chain broken at entry {report.broken_at}: it {report.reason}.", icon=":material/gpp_bad:")
    entries = load_audit(session, limit=200)
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "#": e.id,
                    "Time (UTC)": e.ts.strftime("%d %b %Y %H:%M:%S"),
                    "User": e.username,
                    "Action": e.action,
                    "Record": f"{e.entity} {e.entity_id}",
                    "Previous hash": e.prev_hash[:12] + "...",
                    "Entry hash": e.entry_hash[:12] + "...",
                }
                for e in entries
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    st.download_button(
        "Download full audit trail (CSV)",
        audit_csv(session),
        file_name="governiq-audit-trail.csv",
        mime="text/csv",
        icon=":material/download:",
    )
    st.caption("An auditor can recompute every hash from the CSV to check the chain independently.")

# ---------- Users ----------
with users_tab:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Username": u.username,
                    "Name": u.full_name,
                    "Role": u.role,
                    "Department": u.department,
                    "Last sign-in (UTC)": u.last_login.strftime("%d %b %Y %H:%M")
                    if u.last_login
                    else "Never",
                    "Failed attempts": u.failed_logins,
                    "Locked until (UTC)": u.locked_until.strftime("%H:%M") if u.locked_until else "",
                }
                for u in users
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    if not can(actor.role, "manage_users"):
        st.info(f"You are signed in as {actor.role}. Only an Admin can unlock accounts or reset passwords.",
                icon=":material/lock:")  # fmt: skip
    else:
        target = st.selectbox("Account", users, format_func=lambda u: f"{u.username} ({u.role})")
        col1, col2 = st.columns(2)
        with col1.form("reset", border=True):
            st.markdown("**Reset password**")
            new = st.text_input("New password", type="password")
            confirm = st.text_input("Confirm password", type="password")
            reset = st.form_submit_button("Set password", type="primary")
        if reset:
            if new != confirm:
                st.error("The two passwords do not match.", icon=":material/error:")
            else:
                try:
                    set_password(session, target.username, new, actor.username)
                except ValueError as problem:
                    st.error(str(problem), icon=":material/error:")
                else:
                    st.session_state["admin_flash"] = ("ok", f"Password reset for {target.username}.")
                    st.rerun()
        with col2.container(border=True):
            st.markdown("**Unlock account**")
            st.caption("Clears failed attempts and any lockout.")
            if st.button("Unlock", disabled=target.locked_until is None and target.failed_logins == 0):
                unlock_user(session, target.username, actor.username)
                st.session_state["admin_flash"] = ("ok", f"{target.username} unlocked.")
                st.rerun()

    if can(actor.role, "manage_users") and demo_mode():
        with st.container(border=True):
            st.markdown("**Reset the public demo**")
            st.caption(
                "Rebuilds every table from the seed data and clears uploaded evidence. Use it when visitors "
                "have changed the demo. The audit trail starts a new chain."
            )
            if st.button("Reset demo data", icon=":material/restart_alt:"):
                rebuild_demo_data(demo_engine())
                with get_session() as fresh:
                    fresh.add(
                        AuditLog(
                            username=actor.username, action="demo_reset", entity="database", entity_id="all"
                        )
                    )
                    fresh.commit()
                st.session_state["admin_flash"] = ("ok", "Demo data rebuilt from the seed files.")
                st.rerun()

# ---------- Permissions ----------
with perms_tab:
    st.dataframe(
        pd.DataFrame(
            [{"Permission": PERMISSION_LABELS[p], **{r: "Yes" if r in roles else "" for r in ROLES}}
             for p, roles in PERMISSIONS.items()]
        ),
        hide_index=True,
        width="stretch",
        height=36 * (len(PERMISSIONS) + 1) + 3,
    )  # fmt: skip
    st.caption(
        "Roles grant permissions; independence rules then narrow them further. For example, an analyst can "
        "record tests but never on a control they own, and the AI Governance Lead can approve go-live but "
        "never for their own system."
    )
