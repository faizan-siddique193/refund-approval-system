"""
Tests for domain models (models.py).

Covers:
- Pydantic validation (field constraints, blank-string guard)
- Enum membership
- Default factory values
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from refund_approval_system.models import (
    ApprovalLevel,
    ApprovalRequest,
    ApprovalStatus,
    AuditEvent,
    CustomerContext,
    LLMAction,
    OrderContext,
    PolicyResult,
    RefundDecision,
    RefundHistory,
    RefundRequest,
    RefundResponse,
    RefundStatus,
)


# --------------------------------------------------------------------------- #
# RefundRequest                                                                 #
# --------------------------------------------------------------------------- #


class TestRefundRequest:
    def test_valid_request(self):
        req = RefundRequest(
            refund_id="REF-001",
            customer_id="CUS-001",
            order_id="ORD-001",
            amount=99.99,
            reason="Item not delivered",
        )
        assert req.refund_id == "REF-001"
        assert req.amount == 99.99

    def test_amount_must_be_positive(self):
        with pytest.raises(ValidationError):
            RefundRequest(
                refund_id="REF-002",
                customer_id="CUS-001",
                order_id="ORD-001",
                amount=0.0,
                reason="zero amount",
            )

    def test_negative_amount_rejected(self):
        with pytest.raises(ValidationError):
            RefundRequest(
                refund_id="REF-003",
                customer_id="CUS-001",
                order_id="ORD-001",
                amount=-5.0,
                reason="negative",
            )

    def test_blank_refund_id_rejected(self):
        with pytest.raises(ValidationError):
            RefundRequest(
                refund_id="   ",
                customer_id="CUS-001",
                order_id="ORD-001",
                amount=10.0,
                reason="blank id",
            )

    def test_blank_reason_rejected(self):
        with pytest.raises(ValidationError):
            RefundRequest(
                refund_id="REF-004",
                customer_id="CUS-001",
                order_id="ORD-001",
                amount=10.0,
                reason="   ",
            )

    def test_whitespace_is_stripped(self):
        req = RefundRequest(
            refund_id="  REF-005  ",
            customer_id=" CUS-001 ",
            order_id=" ORD-001 ",
            amount=5.0,
            reason=" broken item ",
        )
        assert req.refund_id == "REF-005"
        assert req.customer_id == "CUS-001"
        assert req.reason == "broken item"


# --------------------------------------------------------------------------- #
# OrderContext                                                                  #
# --------------------------------------------------------------------------- #


class TestOrderContext:
    def test_construction(self):
        oc = OrderContext(
            order_id="ORD-X",
            customer_id="CUS-X",
            order_total=200.0,
            delivered=True,
            refund_eligible=True,
            evidence_present=False,
        )
        assert oc.evidence_present is False


# --------------------------------------------------------------------------- #
# CustomerContext                                                               #
# --------------------------------------------------------------------------- #


class TestCustomerContext:
    def test_suspicious_flag(self):
        cc = CustomerContext(
            customer_id="CUS-BAD",
            account_status="active",
            suspicious_activity=True,
        )
        assert cc.suspicious_activity is True


# --------------------------------------------------------------------------- #
# RefundHistory                                                                 #
# --------------------------------------------------------------------------- #


class TestRefundHistory:
    def test_zero_history(self):
        rh = RefundHistory(customer_id="CUS-NEW", refund_count_30d=0, total_refunded_30d=0.0)
        assert rh.refund_count_30d == 0


# --------------------------------------------------------------------------- #
# RefundDecision                                                                #
# --------------------------------------------------------------------------- #


class TestRefundDecision:
    def test_confidence_bounds_upper(self):
        with pytest.raises(ValidationError):
            RefundDecision(
                action=LLMAction.REFUND,
                amount=10.0,
                rationale="ok",
                confidence=1.5,
                uncertainty="none",
            )

    def test_confidence_bounds_lower(self):
        with pytest.raises(ValidationError):
            RefundDecision(
                action=LLMAction.REFUND,
                amount=10.0,
                rationale="ok",
                confidence=-0.1,
                uncertainty="none",
            )

    def test_valid_decision(self):
        rd = RefundDecision(
            action=LLMAction.DECLINE,
            amount=0.0,
            rationale="fraud suspected",
            confidence=0.9,
            uncertainty="low",
        )
        assert rd.action == LLMAction.DECLINE


# --------------------------------------------------------------------------- #
# PolicyResult                                                                  #
# --------------------------------------------------------------------------- #


class TestPolicyResult:
    def test_risk_flags_default_to_empty_list(self):
        pr = PolicyResult(
            allowed_action=LLMAction.REFUND,
            approval_required=False,
            reason="auto-approve",
        )
        assert pr.risk_flags == []
        assert pr.approval_level is None


# --------------------------------------------------------------------------- #
# ApprovalRequest                                                               #
# --------------------------------------------------------------------------- #


class TestApprovalRequest:
    def test_default_status_is_pending(self):
        ar = ApprovalRequest(
            approval_id="APR-001",
            refund_id="REF-001",
            order_id="ORD-001",
            amount=250.0,
            required_level=ApprovalLevel.REVIEWER,
        )
        assert ar.status == ApprovalStatus.PENDING

    def test_created_at_auto_set(self):
        ar = ApprovalRequest(
            approval_id="APR-002",
            refund_id="REF-002",
            order_id="ORD-002",
            amount=50.0,
            required_level=ApprovalLevel.MANAGER,
        )
        assert ar.created_at is not None


# --------------------------------------------------------------------------- #
# AuditEvent                                                                    #
# --------------------------------------------------------------------------- #


class TestAuditEvent:
    def test_created_at_auto_set(self):
        ev = AuditEvent(
            refund_id="REF-001",
            event_type="policy_evaluated",
            details="approved",
        )
        assert ev.created_at is not None


# --------------------------------------------------------------------------- #
# RefundResponse                                                                #
# --------------------------------------------------------------------------- #


class TestRefundResponse:
    def test_defaults(self):
        rr = RefundResponse(
            refund_id="REF-001",
            status=RefundStatus.RECEIVED,
            amount=10.0,
        )
        assert rr.approval_required is False
        assert rr.risk_flags == []
        assert rr.transaction_id is None
