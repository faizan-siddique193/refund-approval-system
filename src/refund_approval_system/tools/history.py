from __future__ import annotations

import logging

from refund_approval_system.models import RefundHistory
from refund_approval_system.tools.mock_tools import get_refund_history

logger = logging.getLogger(__name__)


def tool_get_history(customer_id: str) -> RefundHistory:
    logger.info("Tool: fetching refund history for %s", customer_id)
    for attempt in range(3):
        try:
            return get_refund_history(customer_id)
        except RuntimeError:
            if attempt == 2:
                raise
            logger.warning("Retry %d for history %s", attempt + 1, customer_id)
