from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from refund_approval_system.db.database import get_connection
from refund_approval_system.models import (
    ApprovalRequest,
    ApprovalStatus,
    AuditEvent,
    RefundResponse,
)

logger = logging.getLogger(__name__)

_ISO = "%Y-%m-%dT%H:%M:%S.%f"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(_ISO)


# approval table


def save_approval(approval: ApprovalRequest, db_path: str) -> None:
    """Persist a new approval record (status=pending)."""
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO approvals
                (approval_id, refund_id, order_id, amount, required_level,
                 status, reviewer_id, created_at, decided_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval.approval_id,
                approval.refund_id,
                approval.order_id,
                approval.amount,
                approval.required_level.value,
                approval.status.value,
                None,
                approval.created_at.strftime(_ISO),
                None,
            ),
        )
    logger.debug(
        "Saved approval %s for refund %s", approval.approval_id, approval.refund_id
    )


def get_approval(approval_id: str, db_path: str) -> dict | None:
    """Return the approval row as a dict, or None if not found."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
        ).fetchone()
    return dict(row) if row else None


def update_approval_decision(
    approval_id: str,
    status: ApprovalStatus,
    reviewer_id: str,
    db_path: str,
) -> None:
    """Record the human reviewer's decision on an approval."""
    with get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE approvals
            SET status = ?, reviewer_id = ?, decided_at = ?
            WHERE approval_id = ?
            """,
            (status.value, reviewer_id, _now_iso(), approval_id),
        )
    logger.debug(
        "Updated approval %s to status %s by %s", approval_id, status, reviewer_id
    )


# audit table


def log_audit_event(event: AuditEvent, db_path: str) -> None:
    """Append an audit event to the immutable audit trail."""
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO audit_events (refund_id, event_type, details, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                event.refund_id,
                event.event_type,
                event.details,
                event.created_at.strftime(_ISO),
            ),
        )
    logger.debug("Audit: refund=%s event=%s", event.refund_id, event.event_type)


def get_audit_events(refund_id: str, db_path: str) -> list[dict]:
    """Return all audit events for a given refund, ordered by time."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM audit_events WHERE refund_id = ? ORDER BY id ASC",
            (refund_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# refund table


def upsert_refund_state(response: RefundResponse, db_path: str) -> None:
    """
    Insert or update the current state snapshot of a refund.

    risk_flags is stored as a JSON string so it survives round-trips.
    """
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO refund_states
                (refund_id, status, amount, action, rationale, approval_id,
                 approval_level, risk_flags, transaction_id, error,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                (SELECT created_at FROM refund_states WHERE refund_id = ?), ?
            ), ?)
            ON CONFLICT(refund_id) DO UPDATE SET
                status         = excluded.status,
                action         = excluded.action,
                rationale      = excluded.rationale,
                approval_id    = excluded.approval_id,
                approval_level = excluded.approval_level,
                risk_flags     = excluded.risk_flags,
                transaction_id = excluded.transaction_id,
                error          = excluded.error,
                updated_at     = excluded.updated_at
            """,
            (
                response.refund_id,
                response.status.value,
                response.amount,
                response.action,
                response.rationale,
                response.approval_id,
                response.approval_level.value if response.approval_level else None,
                json.dumps(response.risk_flags),
                response.transaction_id,
                response.error,
                response.refund_id,  # for COALESCE subquery
                _now_iso(),  # created_at when first inserted
                _now_iso(),  # updated_at
            ),
        )


def get_refund_state(refund_id: str, db_path: str) -> RefundResponse | None:
    """Load the latest state snapshot for a refund, or None if not found."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM refund_states WHERE refund_id = ?", (refund_id,)
        ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["risk_flags"] = json.loads(data["risk_flags"] or "[]")
    # Drop DB-only housekeeping columns not present on RefundResponse
    data.pop("created_at", None)
    data.pop("updated_at", None)
    return RefundResponse(**data)
