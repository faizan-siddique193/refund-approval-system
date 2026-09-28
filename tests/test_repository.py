"""
Tests for the repository layer (repository.py).

Each function that touches the database is tested in isolation using a
fresh SQLite database provided by the `db_path` fixture in conftest.py.
"""

from __future__ import annotations

from datetime import datetime

from refund_approval_system.models import (
    ApprovalLevel,
    ApprovalRequest,
    ApprovalStatus,
    AuditEvent,
    RefundResponse,
    RefundStatus,
)
from refund_approval_system.db.repository import (
    get_approval,
    get_audit_events,
    get_refund_state,
    log_audit_event,
    save_approval,
    update_approval_decision,
    upsert_refund_state,
)


# --------------------------------------------------------------------------- #
# Approval table                                                                #
# --------------------------------------------------------------------------- #


class TestApprovalRepository:
    def _make_approval(self, approval_id: str = "APR-001") -> ApprovalRequest:
        return ApprovalRequest(
            approval_id=approval_id,
            refund_id="REF-001",
            order_id="ORD-001",
            amount=250.0,
            required_level=ApprovalLevel.REVIEWER,
        )

    def test_save_and_get_approval(self, db_path):
        approval = self._make_approval()
        save_approval(approval, db_path)
        row = get_approval("APR-001", db_path)
        assert row is not None
        assert row["approval_id"] == "APR-001"
        assert row["refund_id"] == "REF-001"
        assert row["status"] == ApprovalStatus.PENDING.value

    def test_get_approval_not_found(self, db_path):
        result = get_approval("NONEXISTENT", db_path)
        assert result is None

    def test_update_approval_decision_approved(self, db_path):
        approval = self._make_approval()
        save_approval(approval, db_path)
        update_approval_decision("APR-001", ApprovalStatus.APPROVED, "reviewer-42", db_path)
        row = get_approval("APR-001", db_path)
        assert row["status"] == ApprovalStatus.APPROVED.value
        assert row["reviewer_id"] == "reviewer-42"
        assert row["decided_at"] is not None

    def test_update_approval_decision_rejected(self, db_path):
        approval = self._make_approval("APR-002")
        save_approval(approval, db_path)
        update_approval_decision("APR-002", ApprovalStatus.REJECTED, "mgr-01", db_path)
        row = get_approval("APR-002", db_path)
        assert row["status"] == ApprovalStatus.REJECTED.value

    def test_save_multiple_approvals(self, db_path):
        for i in range(3):
            save_approval(self._make_approval(f"APR-{i:03d}"), db_path)
        for i in range(3):
            assert get_approval(f"APR-{i:03d}", db_path) is not None

    def test_required_level_stored_as_value(self, db_path):
        save_approval(
            ApprovalRequest(
                approval_id="APR-MGR",
                refund_id="REF-MGR",
                order_id="ORD-MGR",
                amount=1000.0,
                required_level=ApprovalLevel.MANAGER,
            ),
            db_path,
        )
        row = get_approval("APR-MGR", db_path)
        assert row["required_level"] == "manager"


# --------------------------------------------------------------------------- #
# Audit events table                                                            #
# --------------------------------------------------------------------------- #


class TestAuditRepository:
    def test_log_and_get_events(self, db_path):
        ev = AuditEvent(refund_id="REF-001", event_type="received", details="request accepted")
        log_audit_event(ev, db_path)
        events = get_audit_events("REF-001", db_path)
        assert len(events) == 1
        assert events[0]["event_type"] == "received"

    def test_get_events_empty(self, db_path):
        events = get_audit_events("REF-NOTHING", db_path)
        assert events == []

    def test_events_ordered_by_insertion(self, db_path):
        for i, etype in enumerate(["received", "validating", "policy_check"]):
            log_audit_event(
                AuditEvent(refund_id="REF-ORD", event_type=etype, details=f"step {i}"),
                db_path,
            )
        events = get_audit_events("REF-ORD", db_path)
        assert [e["event_type"] for e in events] == ["received", "validating", "policy_check"]

    def test_events_isolated_by_refund_id(self, db_path):
        log_audit_event(AuditEvent(refund_id="REF-A", event_type="a", details="a"), db_path)
        log_audit_event(AuditEvent(refund_id="REF-B", event_type="b", details="b"), db_path)
        assert len(get_audit_events("REF-A", db_path)) == 1
        assert len(get_audit_events("REF-B", db_path)) == 1

    def test_multiple_events_same_refund(self, db_path):
        for _ in range(5):
            log_audit_event(
                AuditEvent(refund_id="REF-MULTI", event_type="ping", details="ok"), db_path
            )
        assert len(get_audit_events("REF-MULTI", db_path)) == 5


# --------------------------------------------------------------------------- #
# Refund state table                                                            #
# --------------------------------------------------------------------------- #


class TestRefundStateRepository:
    def _make_response(self, refund_id: str = "REF-001") -> RefundResponse:
        return RefundResponse(
            refund_id=refund_id,
            status=RefundStatus.RECEIVED,
            amount=100.0,
        )

    def test_upsert_and_get(self, db_path):
        resp = self._make_response()
        upsert_refund_state(resp, db_path)
        loaded = get_refund_state("REF-001", db_path)
        assert loaded is not None
        assert loaded.refund_id == "REF-001"
        assert loaded.status == RefundStatus.RECEIVED
        assert loaded.amount == 100.0

    def test_get_nonexistent_returns_none(self, db_path):
        assert get_refund_state("DOES-NOT-EXIST", db_path) is None

    def test_upsert_updates_status(self, db_path):
        resp = self._make_response()
        upsert_refund_state(resp, db_path)

        resp2 = resp.model_copy(update={"status": RefundStatus.COMPLETED})
        upsert_refund_state(resp2, db_path)

        loaded = get_refund_state("REF-001", db_path)
        assert loaded.status == RefundStatus.COMPLETED

    def test_upsert_preserves_created_at(self, db_path):
        """created_at must not change on subsequent upserts."""
        resp = self._make_response()
        upsert_refund_state(resp, db_path)

        from refund_approval_system.db.database import get_connection
        with get_connection(db_path) as conn:
            first_created = conn.execute(
                "SELECT created_at FROM refund_states WHERE refund_id = ?", ("REF-001",)
            ).fetchone()[0]

        upsert_refund_state(resp.model_copy(update={"status": RefundStatus.ANALYZING}), db_path)

        with get_connection(db_path) as conn:
            second_created = conn.execute(
                "SELECT created_at FROM refund_states WHERE refund_id = ?", ("REF-001",)
            ).fetchone()[0]

        assert first_created == second_created

    def test_risk_flags_roundtrip(self, db_path):
        resp = RefundResponse(
            refund_id="REF-FLAGS",
            status=RefundStatus.POLICY_CHECK,
            amount=200.0,
            risk_flags=["missing_evidence", "repeated_refunds_30d"],
        )
        upsert_refund_state(resp, db_path)
        loaded = get_refund_state("REF-FLAGS", db_path)
        assert loaded.risk_flags == ["missing_evidence", "repeated_refunds_30d"]

    def test_optional_fields_roundtrip(self, db_path):
        resp = RefundResponse(
            refund_id="REF-OPT",
            status=RefundStatus.COMPLETED,
            amount=50.0,
            action="refund",
            rationale="auto-approve",
            approval_required=True,
            approval_id="APR-001",
            approval_level=ApprovalLevel.REVIEWER,
            transaction_id="TXN-999",
        )
        upsert_refund_state(resp, db_path)
        loaded = get_refund_state("REF-OPT", db_path)
        assert loaded.action == "refund"
        assert loaded.approval_id == "APR-001"
        assert loaded.approval_level == ApprovalLevel.REVIEWER
        assert loaded.transaction_id == "TXN-999"

    def test_multiple_refunds_independent(self, db_path):
        for i in range(3):
            upsert_refund_state(
                RefundResponse(
                    refund_id=f"REF-{i:03d}",
                    status=RefundStatus.RECEIVED,
                    amount=float(i * 10 + 10),
                ),
                db_path,
            )
        for i in range(3):
            loaded = get_refund_state(f"REF-{i:03d}", db_path)
            assert loaded.amount == float(i * 10 + 10)
