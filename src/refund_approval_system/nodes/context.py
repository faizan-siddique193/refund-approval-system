import logging
from refund_approval_system.agent.state import WorkflowState
from refund_approval_system.models import RefundRequest, RefundStatus
from refund_approval_system.tools import tool_get_order, tool_get_customer, tool_get_history
from refund_approval_system.nodes.helpers import _audit, _snapshot

logger = logging.getLogger(__name__)

def retrieve_context(state: WorkflowState) -> dict:
    request: RefundRequest = state["request"]
    logger.info("retrieve_context: fetching context for refund %s", request.refund_id)
    _audit(state, "retrieve_context", "Fetching order, customer, and refund history")
    _snapshot(state, RefundStatus.RETRIEVING_CONTEXT)

    order = None
    customer = None
    history = None
    errors: list[str] = []

    try:
        order = tool_get_order(request.order_id)
    except RuntimeError as exc:
        logger.error("Order service error: %s", exc)
        errors.append(f"order_service: {exc}")

    try:
        customer = tool_get_customer(request.customer_id)
    except RuntimeError as exc:
        logger.error("Customer service error: %s", exc)
        errors.append(f"customer_service: {exc}")

    try:
        history = tool_get_history(request.customer_id)
    except RuntimeError as exc:
        logger.error("History service error: %s", exc)
        errors.append(f"history_service: {exc}")

    update: dict = {
        "order": order,
        "customer": customer,
        "history": history,
        "status": RefundStatus.RETRIEVING_CONTEXT,
    }
    if errors:
        update["error"] = "; ".join(errors)

    return update
