import logging
import uuid
from refund_approval_system.agent.state import WorkflowState
from refund_approval_system.models import RefundRequest, RefundStatus, ApprovalRequest, ApprovalStatus, ApprovalLevel
from refund_approval_system.db.repository import save_approval, get_approval, update_approval_decision
from refund_approval_system.nodes.helpers import _audit, _snapshot

logger = logging.getLogger(__name__)

def create_approval(state: WorkflowState) -> dict:
    request: RefundRequest = state["request"]
    policy = state["policy_result"]
    approval_id = f"APR-{uuid.uuid4().hex[:8].upper()}"

    logger.info(
        "create_approval: creating approval %s (level=%s) for refund %s",
        approval_id,
        policy.approval_level,
        request.refund_id,
    )

    approval = ApprovalRequest(
        approval_id=approval_id,
        refund_id=request.refund_id,
        order_id=request.order_id,
        amount=request.amount,
        required_level=policy.approval_level or ApprovalLevel.REVIEWER,
        status=ApprovalStatus.PENDING,
    )

    db_path = state.get("db_path")
    if db_path:
        save_approval(approval, db_path)

    _audit(
        state,
        "approval_created",
        f"approval_id={approval_id} level={policy.approval_level}",
    )
    _snapshot(
        state,
        RefundStatus.WAITING_FOR_APPROVAL,
        approval_id=approval_id,
    )

    return {
        "approval_id": approval_id,
        "status": RefundStatus.WAITING_FOR_APPROVAL,
    }

def process_approval(state: WorkflowState) -> dict:
    approval_result = state.get("approval_result")
    request = state["request"]
    policy = state.get("policy_result")
    db_path = state.get("db_path")

    if not approval_result:
        return {"status": RefundStatus.FAILED, "error": "Approval result is missing."}

    if db_path:
        db_approval = get_approval(approval_result.approval_id, db_path)
        if not db_approval:
            return {"status": RefundStatus.FAILED, "error": "Approval record not found."}
        if db_approval["status"] != ApprovalStatus.PENDING.value:
            return {"status": RefundStatus.FAILED, "error": f"Approval is not pending (status: {db_approval['status']})."}

    if approval_result.refund_id != request.refund_id:
        return {"status": RefundStatus.FAILED, "error": "Refund ID mismatch in approval."}
    if approval_result.order_id != request.order_id:
        return {"status": RefundStatus.FAILED, "error": "Order ID mismatch in approval."}
    if approval_result.amount != request.amount:
        return {"status": RefundStatus.FAILED, "error": "Amount mismatch in approval."}

    if policy:
        required_level = policy.approval_level
        if required_level == ApprovalLevel.MANAGER and approval_result.reviewer_role != ApprovalLevel.MANAGER:
            return {"status": RefundStatus.FAILED, "error": "Insufficient approval authority."}

    if db_path:
        update_approval_decision(
            approval_result.approval_id, 
            approval_result.decision, 
            approval_result.reviewer_id, 
            db_path
        )

    if approval_result.decision == ApprovalStatus.APPROVED:
        _audit(state, "approval_processed", f"decision={approval_result.decision.value} by {approval_result.reviewer_id}")
        return {"status": RefundStatus.APPROVED}
    elif approval_result.decision == ApprovalStatus.REJECTED:
        _audit(state, "approval_processed", f"decision={approval_result.decision.value} by {approval_result.reviewer_id}")
        return {"status": RefundStatus.REJECTED, "error": "Refund was rejected by human reviewer."}
    else:
        return {"status": RefundStatus.FAILED, "error": f"Invalid decision: {approval_result.decision}"}
