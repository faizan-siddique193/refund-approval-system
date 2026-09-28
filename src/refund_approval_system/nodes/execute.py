import logging
from refund_approval_system.agent.state import WorkflowState
from refund_approval_system.models import RefundRequest, RefundStatus
from refund_approval_system.tools import execute_refund_payment
from refund_approval_system.db.repository import get_refund_state
from refund_approval_system.nodes.helpers import _audit, _snapshot

logger = logging.getLogger(__name__)

def execute_refund(state: WorkflowState) -> dict:
    request: RefundRequest = state["request"]
    db_path = state.get("db_path")

    if db_path:
        existing = get_refund_state(request.refund_id, db_path)
        if existing and existing.status in [RefundStatus.COMPLETED, RefundStatus.EXECUTING]:
            logger.warning("execute_refund: refund %s is already %s", request.refund_id, existing.status.value)
            return {"status": existing.status, "error": "Duplicate execution prevented."}

    logger.info("execute_refund: executing refund %s for $%.2f", request.refund_id, request.amount)
    _audit(state, "execute_refund", f"Submitting payment refund for ${request.amount:.2f}")
    _snapshot(state, RefundStatus.EXECUTING)

    result = execute_refund_payment(refund_id=request.refund_id, amount=request.amount)

    if result.success:
        logger.info(
            "execute_refund: SUCCESS transaction_id=%s for refund %s",
            result.transaction_id,
            request.refund_id,
        )
        _audit(state, "refund_completed", f"transaction_id={result.transaction_id}")
        _snapshot(state, RefundStatus.COMPLETED, transaction_id=result.transaction_id)
        return {
            "transaction_id": result.transaction_id,
            "status": RefundStatus.COMPLETED,
        }
    else:
        logger.error(
            "execute_refund: FAILED for refund %s: %s", request.refund_id, result.error
        )
        _audit(state, "refund_failed", f"error={result.error}")
        _snapshot(state, RefundStatus.FAILED, error=result.error)
        return {
            "status": RefundStatus.FAILED,
            "error": result.error or "Payment processor returned failure.",
        }
