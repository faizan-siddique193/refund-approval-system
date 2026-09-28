import logging
from typing import Any
from refund_approval_system.agent.state import WorkflowState
from refund_approval_system.models import RefundRequest, RefundStatus, AuditEvent, RefundResponse
from refund_approval_system.db.repository import log_audit_event, upsert_refund_state

def _audit(state: WorkflowState, event_type: str, details: str) -> None:
    db_path = state.get("db_path")
    request: RefundRequest = state["request"]
    if db_path:
        log_audit_event(
            AuditEvent(
                refund_id=request.refund_id,
                event_type=event_type,
                details=details,
            ),
            db_path,
        )

def _snapshot(state: WorkflowState, status: RefundStatus, **overrides: Any) -> None:
    db_path = state.get("db_path")
    if not db_path:
        return
    request: RefundRequest = state["request"]
    policy = state.get("policy_result")
    llm = state.get("llm_decision")
    resp = RefundResponse(
        refund_id=request.refund_id,
        status=status,
        amount=request.amount,
        action=overrides.get("action", llm.action.value if llm else None),
        rationale=overrides.get("rationale", llm.rationale if llm else None),
        approval_required=policy.approval_required if policy else False,
        approval_id=overrides.get("approval_id", state.get("approval_id")),
        approval_level=policy.approval_level if policy else None,
        risk_flags=policy.risk_flags if policy else [],
        transaction_id=overrides.get("transaction_id", state.get("transaction_id")),
        error=overrides.get("error", state.get("error")),
    )
    upsert_refund_state(resp, db_path)
