from __future__ import annotations

import logging
import uuid

from refund_approval_system.models import RefundExecutionResult

logger = logging.getLogger(__name__)

def execute_refund_payment(refund_id: str, amount: float) -> RefundExecutionResult:
    """
    Submit the refund to the (mock) payment processor.

    In production this would call a real payments API.  The mock always
    succeeds, returning a generated transaction ID so end-to-end tests
    can assert on it.

    This tool MUST NOT be called from analysis, policy, or routing nodes.
    Only ``execute_refund`` (the terminal action node) may invoke it.
    """
    transaction_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
    logger.info(
        "Tool: executing refund %s for $%.2f → transaction %s",
        refund_id,
        amount,
        transaction_id,
    )
    return RefundExecutionResult(success=True, transaction_id=transaction_id)
