from __future__ import annotations

import logging

from refund_approval_system.models import OrderContext
from refund_approval_system.tools.mock_tools import get_order_details

logger = logging.getLogger(__name__)


def tool_get_order(order_id: str) -> OrderContext | None:
    logger.info("Tool: fetching order %s", order_id)
    for attempt in range(3):
        try:
            return get_order_details(order_id)
        except RuntimeError:
            if attempt == 2:
                raise
            logger.warning("Retry %d for order %s", attempt + 1, order_id)
