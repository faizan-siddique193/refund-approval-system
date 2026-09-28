"""
Mock data-retrieval tools representing external upstream services.

In production these would call real APIs/databases. For this assignment they
return in-memory data to keep the system self-contained and testable.

Each tool can optionally simulate a failure -- useful for testing the
agent's failure-handling path without requiring an actual broken service.
"""

from __future__ import annotations

import logging
from typing import Optional

from refund_approval_system.models import (
    CustomerContext,
    OrderContext,
    RefundHistory,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mock data stores
# ---------------------------------------------------------------------------

_ORDERS: dict[str, OrderContext] = {
    "ORD-1001": OrderContext(
        order_id="ORD-1001",
        customer_id="CUS-001",
        order_total=120.0,
        delivered=True,
        refund_eligible=True,
        evidence_present=True,
    ),
    "ORD-1002": OrderContext(
        order_id="ORD-1002",
        customer_id="CUS-002",
        order_total=900.0,
        delivered=True,
        refund_eligible=True,
        evidence_present=True,
    ),
    # Additional test fixtures
    "ORD-1003": OrderContext(
        order_id="ORD-1003",
        customer_id="CUS-003",
        order_total=75.0,
        delivered=True,
        refund_eligible=True,
        evidence_present=False,   # Risk C: missing evidence
    ),
    "ORD-1004": OrderContext(
        order_id="ORD-1004",
        customer_id="CUS-004",
        order_total=200.0,
        delivered=True,
        refund_eligible=False,    # Business rule: not eligible
        evidence_present=True,
    ),
    "ORD-1005": OrderContext(
        order_id="ORD-1005",
        customer_id="CUS-005",
        order_total=35.0,
        delivered=True,
        refund_eligible=True,
        evidence_present=True,    # Belongs to CUS-005 -- mismatch test uses CUS-001
    ),
}

_CUSTOMERS: dict[str, CustomerContext] = {
    "CUS-001": CustomerContext(
        customer_id="CUS-001",
        account_status="active",
        suspicious_activity=False,
    ),
    "CUS-002": CustomerContext(
        customer_id="CUS-002",
        account_status="active",
        suspicious_activity=False,
    ),
    "CUS-003": CustomerContext(
        customer_id="CUS-003",
        account_status="active",
        suspicious_activity=False,
    ),
    "CUS-004": CustomerContext(
        customer_id="CUS-004",
        account_status="active",
        suspicious_activity=False,
    ),
    "CUS-005": CustomerContext(
        customer_id="CUS-005",
        account_status="active",
        suspicious_activity=False,
    ),
    "CUS-SUSP": CustomerContext(
        customer_id="CUS-SUSP",
        account_status="active",
        suspicious_activity=True,   # Risk D
    ),
    "CUS-SUSP-ORD": CustomerContext(
        customer_id="CUS-SUSP-ORD",
        account_status="active",
        suspicious_activity=True,
    ),
}

_ORDERS["ORD-SUSP"] = OrderContext(
    order_id="ORD-SUSP",
    customer_id="CUS-SUSP",
    order_total=45.0,
    delivered=True,
    refund_eligible=True,
    evidence_present=True,
)

_REFUND_HISTORY: dict[str, RefundHistory] = {
    "CUS-001": RefundHistory(customer_id="CUS-001", refund_count_30d=0, total_refunded_30d=0.0),
    "CUS-002": RefundHistory(customer_id="CUS-002", refund_count_30d=1, total_refunded_30d=50.0),
    "CUS-003": RefundHistory(customer_id="CUS-003", refund_count_30d=3, total_refunded_30d=150.0),  # Risk A
    "CUS-004": RefundHistory(customer_id="CUS-004", refund_count_30d=0, total_refunded_30d=0.0),
    "CUS-005": RefundHistory(customer_id="CUS-005", refund_count_30d=0, total_refunded_30d=0.0),
    "CUS-SUSP": RefundHistory(customer_id="CUS-SUSP", refund_count_30d=0, total_refunded_30d=0.0),
    "CUS-SUSP-ORD": RefundHistory(customer_id="CUS-SUSP-ORD", refund_count_30d=0, total_refunded_30d=0.0),
}

# Add a high-repeat customer for Test E
_CUSTOMERS["CUS-REPEAT"] = CustomerContext(
    customer_id="CUS-REPEAT",
    account_status="active",
    suspicious_activity=False,
)
_ORDERS["ORD-REPEAT"] = OrderContext(
    order_id="ORD-REPEAT",
    customer_id="CUS-REPEAT",
    order_total=30.0,
    delivered=True,
    refund_eligible=True,
    evidence_present=True,
)
_REFUND_HISTORY["CUS-REPEAT"] = RefundHistory(
    customer_id="CUS-REPEAT",
    refund_count_30d=3,    # 3 refunds -> Risk A triggers even on low-value amount
    total_refunded_30d=90.0,
)

# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

# Failure simulation flags -- toggled by tests
_FAIL_ORDER = False
_FAIL_CUSTOMER = False
_FAIL_HISTORY = False


def set_tool_failure(order: bool = False, customer: bool = False, history: bool = False) -> None:
    """
    Test helper: force specific tools to raise exceptions.

    Call with all False to reset.  NOT for production use.
    """
    global _FAIL_ORDER, _FAIL_CUSTOMER, _FAIL_HISTORY
    _FAIL_ORDER = order
    _FAIL_CUSTOMER = customer
    _FAIL_HISTORY = history


def get_order_details(order_id: str) -> Optional[OrderContext]:
    """
    Retrieve order details from the (mocked) order management system.

    Returns None if the order is not found.
    Raises RuntimeError when the failure flag is set (test mode).
    """
    if _FAIL_ORDER:
        raise RuntimeError("Order service is unavailable (simulated failure)")

    result = _ORDERS.get(order_id)
    if result is None:
        logger.warning("Order not found: %s", order_id)
    else:
        logger.debug("Order retrieved: %s", order_id)
    return result


def get_customer_account(customer_id: str) -> Optional[CustomerContext]:
    """
    Retrieve customer account details from the (mocked) CRM.

    Returns None if the customer is not found.
    Raises RuntimeError when the failure flag is set (test mode).
    """
    if _FAIL_CUSTOMER:
        raise RuntimeError("Customer service is unavailable (simulated failure)")

    result = _CUSTOMERS.get(customer_id)
    if result is None:
        logger.warning("Customer not found: %s", customer_id)
    else:
        logger.debug("Customer retrieved: %s", customer_id)
    return result


def get_refund_history(customer_id: str) -> RefundHistory:
    """
    Retrieve the customer's 30-day refund history.

    Returns a zero-count history for unknown customers (conservative default).
    Raises RuntimeError when the failure flag is set (test mode).
    """
    if _FAIL_HISTORY:
        raise RuntimeError("Refund history service is unavailable (simulated failure)")

    result = _REFUND_HISTORY.get(
        customer_id,
        RefundHistory(customer_id=customer_id, refund_count_30d=0, total_refunded_30d=0.0),
    )
    logger.debug("Refund history retrieved for %s: %d refunds", customer_id, result.refund_count_30d)
    return result
