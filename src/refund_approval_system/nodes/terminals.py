import logging
from refund_approval_system.agent.state import WorkflowState
from refund_approval_system.models import RefundRequest, RefundStatus
from refund_approval_system.nodes.helpers import _audit, _snapshot

logger = logging.getLogger(__name__)

def escalate(state: WorkflowState) -> dict:
    request: RefundRequest = state["request"]
    policy = state.get("policy_result")
    reason = policy.reason if policy else "Escalation triggered by workflow."

    logger.info("escalate: refund %s — %s", request.refund_id, reason)
    _audit(state, "escalated", reason)
    _snapshot(state, RefundStatus.ESCALATED, error=reason)

    return {"status": RefundStatus.ESCALATED}

def decline(state: WorkflowState) -> dict:
    request: RefundRequest = state["request"]
    policy = state.get("policy_result")
    reason = policy.reason if policy else "Declined by policy."

    logger.info("decline: refund %s — %s", request.refund_id, reason)
    _audit(state, "declined", reason)
    _snapshot(state, RefundStatus.DECLINED, error=reason)

    return {"status": RefundStatus.DECLINED}

def failed(state: WorkflowState) -> dict:
    request: RefundRequest = state["request"]
    error = state.get("error", "Unexpected workflow failure.")
    logger.error("failed: refund %s — %s", request.refund_id, error)
    _audit(state, "failed", error)
    _snapshot(state, RefundStatus.FAILED, error=error)
    return {"status": RefundStatus.FAILED}

def reject_refund(state: WorkflowState) -> dict:
    request: RefundRequest = state["request"]
    error = state.get("error", "Rejected by human reviewer.")
    logger.info("reject_refund: refund %s — %s", request.refund_id, error)
    _audit(state, "rejected", error)
    _snapshot(state, RefundStatus.REJECTED, error=error)
    return {"status": RefundStatus.REJECTED}
