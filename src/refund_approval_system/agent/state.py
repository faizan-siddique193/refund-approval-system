from __future__ import annotations

from typing_extensions import TypedDict

from refund_approval_system.models import (
    ApprovalResult,
    CustomerContext,
    OrderContext,
    PolicyResult,
    RefundDecision,
    RefundHistory,
    RefundRequest,
    RefundStatus,
)


class WorkflowState(TypedDict, total=False):
    #  request input
    request: RefundRequest
    """The validated incoming refund request."""

    db_path: str
    """Path to the SQLite database. Injected at invocation time."""

    # order context
    order: OrderContext | None
    """Order details fetched from the (mock) order service."""

    customer: CustomerContext | None
    """Customer account details fetched from the (mock) CRM."""

    history: RefundHistory | None
    """Customer's 30-day refund history."""

    # analysis
    llm_decision: RefundDecision | None
    """Advisory recommendation produced by the LLM (never authoritative)."""

    #  policy check
    policy_result: PolicyResult | None
    """Authoritative, deterministic policy engine output."""

    # approval
    approval_id: str | None
    """UUID of the ApprovalRequest record written to the database."""

    approval_result: ApprovalResult | None
    """The result of the human approval, passed in when resuming the graph."""
    # execution outcome
    transaction_id: str | None
    """Payment-processor transaction ID returned after a successful refund."""

    # terminal status or error
    status: RefundStatus
    """Current lifecycle status of the refund request."""

    error: str | None
    """Human-readable error description if a node fails softly."""
