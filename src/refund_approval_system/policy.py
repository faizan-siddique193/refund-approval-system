"""
Deterministic Policy Engine.

This module is the single authoritative source for refund authorization rules.
It does NOT call the LLM, does NOT execute refunds, and cannot be overridden
by LLM output or user-supplied text.

Rules implemented:
  Rule 1  -- Low-value (<$50): auto-approve if no risk flags.
  Rule 2  -- Standard ($50-$500): reviewer approval required.
  Rule 3  -- High-value (>$500): manager approval required.
  Risk A  -- repeated refunds (>=3 in 30d): force human review.
  Risk B  -- customer/order mismatch: escalate immediately.
  Risk C  -- missing evidence: human review required.
  Risk D  -- suspicious account activity: manager approval required.
"""

from __future__ import annotations

import logging

from refund_approval_system.models import (
    ApprovalLevel,
    CustomerContext,
    LLMAction,
    OrderContext,
    PolicyResult,
    RefundHistory,
    RefundRequest,
)

logger = logging.getLogger(__name__)

AUTO_APPROVE_MAX = 50.0
REVIEWER_MAX = 500.0
REPEAT_REFUND_THRESHOLD = 3


def evaluate_policy(
    request: RefundRequest,
    order: OrderContext | None,
    customer: CustomerContext | None,
    history: RefundHistory | None,
) -> PolicyResult:
    """
    Evaluate all deterministic business and risk rules for a refund request.

    Parameters
    ----------
    request:  The validated refund request (authoritative amount & IDs).
    order:    Retrieved order context (None if retrieval failed).
    customer: Retrieved customer context (None if retrieval failed).
    history:  Retrieved refund history (None if retrieval failed).

    Returns
    -------
    PolicyResult with the authoritative decision.  The LLM decision is NOT
    consulted here -- policy is fully deterministic.
    """
    risk_flags: list[str] = []
    approval_required = False
    approval_level: ApprovalLevel | None = None
    allowed_action = LLMAction.REFUND
    reason_parts: list[str] = []

    # missing context
    if order is None:
        logger.warning("Order context unavailable for refund %s", request.refund_id)
        risk_flags.append("order_context_unavailable")
        return PolicyResult(
            allowed_action=LLMAction.ESCALATE,
            approval_required=False,
            approval_level=None,
            risk_flags=risk_flags,
            reason="Order details could not be retrieved. Cannot authorize refund.",
        )

    if customer is None:
        logger.warning("Customer context unavailable for refund %s", request.refund_id)
        risk_flags.append("customer_context_unavailable")
        return PolicyResult(
            allowed_action=LLMAction.ESCALATE,
            approval_required=False,
            approval_level=None,
            risk_flags=risk_flags,
            reason="Customer details could not be retrieved. Cannot authorize refund.",
        )

    # customer or oder mismatch
    if request.customer_id != order.customer_id:
        logger.warning(
            "Customer/order mismatch: request.customer_id=%s, order.customer_id=%s",
            request.customer_id,
            order.customer_id,
        )
        risk_flags.append("customer_order_mismatch")
        return PolicyResult(
            allowed_action=LLMAction.ESCALATE,
            approval_required=False,
            approval_level=None,
            risk_flags=risk_flags,
            reason=(
                f"Customer ID on request ({request.customer_id}) does not match "
                f"the order owner ({order.customer_id}). Escalating for investigation."
            ),
        )

    # order must be refund eligible
    if not order.refund_eligible:
        risk_flags.append("order_not_refund_eligible")
        return PolicyResult(
            allowed_action=LLMAction.DECLINE,
            approval_required=False,
            approval_level=None,
            risk_flags=risk_flags,
            reason="Order is not eligible for a refund per business rules.",
        )

    #  suspicious account activity
    if customer.suspicious_activity:
        risk_flags.append("suspicious_account_activity")
        approval_required = True
        approval_level = ApprovalLevel.MANAGER
        reason_parts.append("Suspicious account activity detected.")

    #    missing evidance
    if not order.evidence_present:
        risk_flags.append("missing_evidence")
        approval_required = True
        if approval_level is None:
            approval_level = ApprovalLevel.REVIEWER
        reason_parts.append("No supporting evidence on file.")

    # repeated refunds in the last 30 days
    if history is not None and history.refund_count_30d >= REPEAT_REFUND_THRESHOLD:
        risk_flags.append("repeated_refunds_30d")
        approval_required = True
        if approval_level is None:
            approval_level = ApprovalLevel.REVIEWER
        reason_parts.append(
            f"Customer has made {history.refund_count_30d} refunds in the last 30 days."
        )

    #    High value refund geater than 500
    if request.amount > REVIEWER_MAX:
        approval_required = True
        approval_level = ApprovalLevel.MANAGER  # manager always overrides reviewer
        reason_parts.append(
            f"High-value refund (${request.amount:.2f}) requires manager approval."
        )

    # Rule 2: Standard refund  ($50 <= amount <= $500)
    elif request.amount >= AUTO_APPROVE_MAX:
        approval_required = True
        if approval_level is None:
            approval_level = ApprovalLevel.REVIEWER
        reason_parts.append(
            f"Standard refund (${request.amount:.2f}) requires reviewer approval."
        )

    # Rule 1: Low-value refund  (amount < $50, no blocking risk flags)
    # Build human-readable reason summary
    if not reason_parts:
        reason = (
            f"Low-value refund (${request.amount:.2f}) with no risk flags. "
            "Auto-approval granted."
        )
    else:
        reason = " | ".join(reason_parts)

    # Decide final allowed_action
    if approval_required:
        allowed_action = LLMAction.REFUND  # still a refund, but gated on approval
    else:
        allowed_action = LLMAction.REFUND  # auto-execute path

    logger.info(
        "Policy result for %s: allowed_action=%s, approval_required=%s, "
        "approval_level=%s, risk_flags=%s",
        request.refund_id,
        allowed_action,
        approval_required,
        approval_level,
        risk_flags,
    )

    return PolicyResult(
        allowed_action=allowed_action,
        approval_required=approval_required,
        approval_level=approval_level,
        risk_flags=risk_flags,
        reason=reason,
    )
