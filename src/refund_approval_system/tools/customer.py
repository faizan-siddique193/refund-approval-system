from __future__ import annotations

import logging

from refund_approval_system.models import CustomerContext
from refund_approval_system.tools.mock_tools import get_customer_account

logger = logging.getLogger(__name__)


def tool_get_customer(customer_id: str) -> CustomerContext | None:
    logger.info("Tool: fetching customer %s", customer_id)
    for attempt in range(3):
        try:
            return get_customer_account(customer_id)
        except RuntimeError:
            if attempt == 2:
                raise
            logger.warning("Retry %d for customer %s", attempt + 1, customer_id)
