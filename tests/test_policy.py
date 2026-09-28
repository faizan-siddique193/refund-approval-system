"""
Tests for the deterministic policy engine (policy.py).

Each test maps to a named rule or risk flag.  No LLM or DB involved.
"""

from __future__ import annotations

import pytest

from refund_approval_system.models import (
    ApprovalLevel,
    CustomerContext,
    LLMAction,
    OrderContext,
    RefundHistory,
    RefundRequest,
)
from refund_approval_system.policy import (
    AUTO_APPROVE_MAX,
    REPEAT_REFUND_THRESHOLD,
    REVIEWER_MAX,
    evaluate_policy,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _req(amount: float, customer_id: str = "CUS-001", order_id: str = "ORD-001") -> RefundRequest:
    return RefundRequest(
        refund_id="REF-TEST",
        customer_id=customer_id,
        order_id=order_id,
        amount=amount,
        reason="test",
    )


def _order(
    customer_id: str = "CUS-001",
    order_total: float = 100.0,
    refund_eligible: bool = True,
    evidence_present: bool = True,
) -> OrderContext:
    return OrderContext(
        order_id="ORD-001",
        customer_id=customer_id,
        order_total=order_total,
        delivered=True,
        refund_eligible=refund_eligible,
        evidence_present=evidence_present,
    )


def _customer(suspicious: bool = False) -> CustomerContext:
    return CustomerContext(
        customer_id="CUS-001",
        account_status="active",
        suspicious_activity=suspicious,
    )


def _history(count: int = 0, total: float = 0.0) -> RefundHistory:
    return RefundHistory(customer_id="CUS-001", refund_count_30d=count, total_refunded_30d=total)


# --------------------------------------------------------------------------- #
# Rule 1: Low-value auto-approval                                               #
# --------------------------------------------------------------------------- #


class TestRule1LowValue:
    """Amounts strictly below AUTO_APPROVE_MAX ($50) with no risk flags → auto-approve."""

    def test_auto_approve_low_value(self):
        result = evaluate_policy(_req(25.0), _order(), _customer(), _history())
        assert result.allowed_action == LLMAction.REFUND
        assert result.approval_required is False
        assert result.approval_level is None
        assert result.risk_flags == []

    def test_boundary_just_below_auto_max(self):
        result = evaluate_policy(_req(AUTO_APPROVE_MAX - 0.01), _order(), _customer(), _history())
        assert result.approval_required is False

    def test_zero_history_auto_approve(self):
        result = evaluate_policy(_req(10.0), _order(), _customer(), _history(0, 0.0))
        assert result.approval_required is False


# --------------------------------------------------------------------------- #
# Rule 2: Standard refund – reviewer approval                                   #
# --------------------------------------------------------------------------- #


class TestRule2Standard:
    """Amounts between $50 and $500 (inclusive) → reviewer approval."""

    def test_exactly_at_auto_max(self):
        result = evaluate_policy(_req(AUTO_APPROVE_MAX), _order(), _customer(), _history())
        assert result.approval_required is True
        assert result.approval_level == ApprovalLevel.REVIEWER

    def test_mid_range_needs_reviewer(self):
        result = evaluate_policy(_req(250.0), _order(), _customer(), _history())
        assert result.approval_required is True
        assert result.approval_level == ApprovalLevel.REVIEWER

    def test_at_reviewer_max(self):
        result = evaluate_policy(_req(REVIEWER_MAX), _order(), _customer(), _history())
        assert result.approval_required is True
        assert result.approval_level == ApprovalLevel.REVIEWER


# --------------------------------------------------------------------------- #
# Rule 3: High-value – manager approval                                         #
# --------------------------------------------------------------------------- #


class TestRule3HighValue:
    """Amounts above $500 → manager approval."""

    def test_above_reviewer_max_needs_manager(self):
        result = evaluate_policy(_req(REVIEWER_MAX + 0.01), _order(), _customer(), _history())
        assert result.approval_required is True
        assert result.approval_level == ApprovalLevel.MANAGER

    def test_large_amount_manager(self):
        result = evaluate_policy(_req(10_000.0), _order(), _customer(), _history())
        assert result.approval_level == ApprovalLevel.MANAGER


# --------------------------------------------------------------------------- #
# Risk A: Repeated refunds                                                      #
# --------------------------------------------------------------------------- #


class TestRiskARepeatedRefunds:
    def test_at_threshold_triggers_flag(self):
        result = evaluate_policy(
            _req(25.0), _order(), _customer(), _history(REPEAT_REFUND_THRESHOLD)
        )
        assert "repeated_refunds_30d" in result.risk_flags
        assert result.approval_required is True

    def test_below_threshold_no_flag(self):
        result = evaluate_policy(
            _req(25.0), _order(), _customer(), _history(REPEAT_REFUND_THRESHOLD - 1)
        )
        assert "repeated_refunds_30d" not in result.risk_flags

    def test_repeat_flag_sets_minimum_reviewer(self):
        """Low-value amount + repeat flag → reviewer approval (not manager)."""
        result = evaluate_policy(
            _req(20.0), _order(), _customer(), _history(REPEAT_REFUND_THRESHOLD)
        )
        assert result.approval_level == ApprovalLevel.REVIEWER

    def test_repeat_plus_high_value_keeps_manager(self):
        """High-value + repeat → manager still wins."""
        result = evaluate_policy(
            _req(600.0), _order(), _customer(), _history(REPEAT_REFUND_THRESHOLD)
        )
        assert result.approval_level == ApprovalLevel.MANAGER


# --------------------------------------------------------------------------- #
# Risk B: Customer / Order mismatch                                             #
# --------------------------------------------------------------------------- #


class TestRiskBMismatch:
    def test_mismatch_escalates(self):
        req = _req(30.0, customer_id="CUS-WRONG", order_id="ORD-001")
        order = _order(customer_id="CUS-REAL")  # order belongs to CUS-REAL
        result = evaluate_policy(req, order, _customer(), _history())
        assert "customer_order_mismatch" in result.risk_flags
        assert result.allowed_action == LLMAction.ESCALATE
        assert result.approval_required is False  # escalated, not queued for approval

    def test_correct_customer_no_mismatch(self):
        result = evaluate_policy(_req(30.0), _order(), _customer(), _history())
        assert "customer_order_mismatch" not in result.risk_flags


# --------------------------------------------------------------------------- #
# Risk C: Missing evidence                                                      #
# --------------------------------------------------------------------------- #


class TestRiskCMissingEvidence:
    def test_missing_evidence_forces_review(self):
        result = evaluate_policy(
            _req(25.0), _order(evidence_present=False), _customer(), _history()
        )
        assert "missing_evidence" in result.risk_flags
        assert result.approval_required is True
        assert result.approval_level == ApprovalLevel.REVIEWER

    def test_evidence_present_no_flag(self):
        result = evaluate_policy(
            _req(25.0), _order(evidence_present=True), _customer(), _history()
        )
        assert "missing_evidence" not in result.risk_flags


# --------------------------------------------------------------------------- #
# Risk D: Suspicious account activity                                           #
# --------------------------------------------------------------------------- #


class TestRiskDSuspicious:
    def test_suspicious_requires_manager(self):
        result = evaluate_policy(_req(25.0), _order(), _customer(suspicious=True), _history())
        assert "suspicious_account_activity" in result.risk_flags
        assert result.approval_level == ApprovalLevel.MANAGER

    def test_clean_account_no_flag(self):
        result = evaluate_policy(_req(25.0), _order(), _customer(suspicious=False), _history())
        assert "suspicious_account_activity" not in result.risk_flags


# --------------------------------------------------------------------------- #
# Business rule: order not refund-eligible                                      #
# --------------------------------------------------------------------------- #


class TestOrderEligibility:
    def test_ineligible_order_declined(self):
        result = evaluate_policy(
            _req(50.0), _order(refund_eligible=False), _customer(), _history()
        )
        assert result.allowed_action == LLMAction.DECLINE
        assert "order_not_refund_eligible" in result.risk_flags

    def test_eligible_order_proceeds(self):
        result = evaluate_policy(
            _req(50.0), _order(refund_eligible=True), _customer(), _history()
        )
        assert result.allowed_action != LLMAction.DECLINE


# --------------------------------------------------------------------------- #
# Guard: missing context                                                        #
# --------------------------------------------------------------------------- #


class TestMissingContext:
    def test_none_order_escalates(self):
        result = evaluate_policy(_req(50.0), None, _customer(), _history())
        assert result.allowed_action == LLMAction.ESCALATE
        assert "order_context_unavailable" in result.risk_flags

    def test_none_customer_escalates(self):
        result = evaluate_policy(_req(50.0), _order(), None, _history())
        assert result.allowed_action == LLMAction.ESCALATE
        assert "customer_context_unavailable" in result.risk_flags

    def test_none_history_does_not_block(self):
        """Missing history is not itself a blocking condition."""
        result = evaluate_policy(_req(25.0), _order(), _customer(), None)
        assert result.allowed_action == LLMAction.REFUND
        assert result.approval_required is False


# --------------------------------------------------------------------------- #
# Rule interaction / priority                                                   #
# --------------------------------------------------------------------------- #


class TestRuleInteractions:
    def test_suspicious_plus_missing_evidence_stays_manager(self):
        """Manager wins over reviewer when both D and C fire."""
        result = evaluate_policy(
            _req(25.0),
            _order(evidence_present=False),
            _customer(suspicious=True),
            _history(),
        )
        assert result.approval_level == ApprovalLevel.MANAGER
        assert "missing_evidence" in result.risk_flags
        assert "suspicious_account_activity" in result.risk_flags

    def test_high_value_plus_suspicious_stays_manager(self):
        result = evaluate_policy(
            _req(600.0),
            _order(),
            _customer(suspicious=True),
            _history(),
        )
        assert result.approval_level == ApprovalLevel.MANAGER

    def test_result_is_deterministic(self):
        """Same inputs must always produce the same output."""
        r1 = evaluate_policy(_req(300.0), _order(), _customer(), _history())
        r2 = evaluate_policy(_req(300.0), _order(), _customer(), _history())
        assert r1.model_dump() == r2.model_dump()
