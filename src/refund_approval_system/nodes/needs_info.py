import logging
from refund_approval_system.agent.state import WorkflowState
from refund_approval_system.models import RefundRequest, RefundStatus
from refund_approval_system.nodes.helpers import _audit, _snapshot

logger = logging.getLogger(__name__)

def needs_information(state: WorkflowState) -> dict:
    request: RefundRequest = state["request"]
    logger.info("needs_information: refund %s needs more info", request.refund_id)
    _audit(state, "needs_information", "LLM determined the request is ambiguous and needs more information.")
    _snapshot(state, RefundStatus.NEEDS_INFORMATION)
    return {"status": RefundStatus.NEEDS_INFORMATION}
