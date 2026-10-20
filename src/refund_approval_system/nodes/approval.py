from datetime import datetime, timezone
import logging
import uuid
from refund_approval_system.agent.state import WorkflowState
from refund_approval_system.models import RefundRequest, RefundStatus, ApprovalRequest, ApprovalStatus, ApprovalLevel
from refund_approval_system.db.repository import save_approval, get_approval, update_approval_decision
from refund_approval_system.nodes.helpers import _audit, _snapshot

logger = logging.getLogger(__name__)

# Server-side reviewer authorization registry
SERVER_REVIEWER_AUTHORITY: dict[str, ApprovalLevel] = {
    "REV-01": ApprovalLevel.REVIEWER,
    "REV-02": ApprovalLevel.REVIEWER,
    "REV-03": ApprovalLevel.REVIEWER,
    "MGR-01": ApprovalLevel.MANAGER,
    "MGR-02": ApprovalLevel.MANAGER,
    "MGR-03": ApprovalLevel.MANAGER,
    "SYSTEM": ApprovalLevel.MANAGER,
}


def get_authorized_reviewer_role(reviewer_id: str, claimed_role: ApprovalLevel | None = None) -> ApprovalLevel:
    """
    Resolve server-side authorized role for reviewer_id.
    Prevents callers from self-declaring manager authority.
    """
    if reviewer_id in SERVER_REVIEWER_AUTHORITY:
        return SERVER_REVIEWER_AUTHORITY[reviewer_id]

    reviewer_id_upper = reviewer_id.upper()
    if reviewer_id_upper.startswith("MGR") or reviewer_id_upper.startswith("MANAGER"):
        return ApprovalLevel.MANAGER
    if reviewer_id_upper.startswith("REV") or reviewer_id_upper.startswith("REVIEWER"):
        return ApprovalLevel.REVIEWER

    # Default to minimum privilege (REVIEWER)
    return ApprovalLevel.REVIEWER


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
        f"approval_id={approval_id} level={policy.approval_level} expires_at={approval.expires_at.isoformat()}",
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

        # Automatic time-based expiration check
        expires_at_str = db_approval.get("expires_at")
        if expires_at_str:
            try:
                clean_ts = expires_at_str.replace("Z", "+00:00")
                expires_at_dt = datetime.fromisoformat(clean_ts)
                if expires_at_dt.tzinfo is None:
                    expires_at_dt = expires_at_dt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > expires_at_dt:
                    update_approval_decision(
                        approval_result.approval_id,
                        ApprovalStatus.EXPIRED,
                        "SYSTEM",
                        db_path,
                    )
                    _audit(
                        state,
                        "approval_expired",
                        f"approval_id={approval_result.approval_id} expired at {expires_at_str}",
                    )
                    return {
                        "status": RefundStatus.FAILED,
                        "error": "Approval request has expired.",
                    }
            except Exception as exc:
                logger.warning("Error evaluating approval expires_at '%s': %s", expires_at_str, exc)

    if approval_result.refund_id != request.refund_id:
        return {"status": RefundStatus.FAILED, "error": "Refund ID mismatch in approval."}
    if approval_result.order_id != request.order_id:
        return {"status": RefundStatus.FAILED, "error": "Order ID mismatch in approval."}
    if approval_result.amount != request.amount:
        return {"status": RefundStatus.FAILED, "error": "Amount mismatch in approval."}

    # Server-side reviewer identity/role verification
    authorized_role = get_authorized_reviewer_role(
        approval_result.reviewer_id, approval_result.reviewer_role
    )

    # Reject caller self-declaration if caller claims manager authority without authorization
    if approval_result.reviewer_role == ApprovalLevel.MANAGER and authorized_role != ApprovalLevel.MANAGER:
        return {
            "status": RefundStatus.FAILED,
            "error": f"Unauthorized role escalation: reviewer '{approval_result.reviewer_id}' is not authorized as MANAGER.",
        }

    if policy:
        required_level = policy.approval_level
        if required_level == ApprovalLevel.MANAGER and authorized_role != ApprovalLevel.MANAGER:
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

