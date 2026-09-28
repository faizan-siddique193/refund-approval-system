import logging
from refund_approval_system.agent.state import WorkflowState
from refund_approval_system.models import RefundRequest, RefundStatus
from refund_approval_system.nodes.helpers import _audit, _snapshot

logger = logging.getLogger(__name__)

def validate_request(state: WorkflowState) -> dict:
    request: RefundRequest | None = state.get("request")
    if request is None:
        return {
            "status": RefundStatus.FAILED,
            "error": "No refund request found in workflow state.",
        }
    logger.info("validate_request: refund_id=%s amount=%.2f", request.refund_id, request.amount)
    _audit(state, "validate_request", f"Validating refund {request.refund_id}")
    _snapshot(state, RefundStatus.VALIDATING)
    return {"status": RefundStatus.VALIDATING}
