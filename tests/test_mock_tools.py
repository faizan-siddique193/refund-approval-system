"""
Tests for the mock external tools (mock_tools.py).

Covers:
- Happy-path lookups for all known fixture IDs
- Missing IDs return None / zero-history defaults
- Failure simulation flags (RuntimeError)
- Tool isolation (failure in one tool doesn't affect others)
"""

from __future__ import annotations

import pytest

from refund_approval_system.tools import mock_tools
from refund_approval_system.tools.mock_tools import (
    get_customer_account,
    get_order_details,
    get_refund_history,
    set_tool_failure,
)


@pytest.fixture(autouse=True)
def reset_failure_flags():
    """Ensure failure flags are cleared before and after every test."""
    set_tool_failure(order=False, customer=False, history=False)
    yield
    set_tool_failure(order=False, customer=False, history=False)


# --------------------------------------------------------------------------- #
# get_order_details                                                             #
# --------------------------------------------------------------------------- #


class TestGetOrderDetails:
    def test_known_order_returned(self):
        order = get_order_details("ORD-1001")
        assert order is not None
        assert order.order_id == "ORD-1001"
        assert order.customer_id == "CUS-001"

    def test_unknown_order_returns_none(self):
        assert get_order_details("ORD-9999") is None

    def test_all_fixture_orders_exist(self):
        for oid in ["ORD-1001", "ORD-1002", "ORD-1003", "ORD-1004", "ORD-1005"]:
            assert get_order_details(oid) is not None, f"{oid} should be in fixtures"

    def test_ineligible_order(self):
        order = get_order_details("ORD-1004")
        assert order.refund_eligible is False

    def test_missing_evidence_order(self):
        order = get_order_details("ORD-1003")
        assert order.evidence_present is False

    def test_order_failure_raises(self):
        set_tool_failure(order=True)
        with pytest.raises(RuntimeError, match="Order service"):
            get_order_details("ORD-1001")

    def test_order_failure_flag_reset(self):
        set_tool_failure(order=True)
        set_tool_failure(order=False)
        order = get_order_details("ORD-1001")
        assert order is not None


# --------------------------------------------------------------------------- #
# get_customer_account                                                          #
# --------------------------------------------------------------------------- #


class TestGetCustomerAccount:
    def test_known_customer_returned(self):
        cust = get_customer_account("CUS-001")
        assert cust is not None
        assert cust.customer_id == "CUS-001"
        assert cust.account_status == "active"
        assert cust.suspicious_activity is False

    def test_unknown_customer_returns_none(self):
        assert get_customer_account("CUS-GHOST") is None

    def test_suspicious_customer(self):
        cust = get_customer_account("CUS-SUSP")
        assert cust is not None
        assert cust.suspicious_activity is True

    def test_customer_failure_raises(self):
        set_tool_failure(customer=True)
        with pytest.raises(RuntimeError, match="Customer service"):
            get_customer_account("CUS-001")

    def test_customer_failure_does_not_affect_order(self):
        set_tool_failure(customer=True)
        order = get_order_details("ORD-1001")
        assert order is not None


# --------------------------------------------------------------------------- #
# get_refund_history                                                            #
# --------------------------------------------------------------------------- #


class TestGetRefundHistory:
    def test_known_history(self):
        hist = get_refund_history("CUS-003")
        assert hist.refund_count_30d == 3  # Risk-A fixture

    def test_unknown_customer_returns_zero_history(self):
        """Unknown customers fall back to zero refunds (safe default)."""
        hist = get_refund_history("CUS-UNKNOWN")
        assert hist.customer_id == "CUS-UNKNOWN"
        assert hist.refund_count_30d == 0
        assert hist.total_refunded_30d == 0.0

    def test_history_failure_raises(self):
        set_tool_failure(history=True)
        with pytest.raises(RuntimeError, match="Refund history service"):
            get_refund_history("CUS-001")

    def test_history_failure_does_not_affect_order_or_customer(self):
        set_tool_failure(history=True)
        assert get_order_details("ORD-1001") is not None
        assert get_customer_account("CUS-001") is not None

    def test_high_repeat_customer(self):
        hist = get_refund_history("CUS-REPEAT")
        assert hist.refund_count_30d == 3

    def test_low_repeat_customer(self):
        hist = get_refund_history("CUS-001")
        assert hist.refund_count_30d == 0


# --------------------------------------------------------------------------- #
# Combined failure isolation                                                    #
# --------------------------------------------------------------------------- #


class TestFailureIsolation:
    def test_all_tools_can_fail_independently(self):
        set_tool_failure(order=True, customer=True, history=True)
        with pytest.raises(RuntimeError):
            get_order_details("ORD-1001")
        with pytest.raises(RuntimeError):
            get_customer_account("CUS-001")
        with pytest.raises(RuntimeError):
            get_refund_history("CUS-001")

    def test_partial_failure_only_one_tool(self):
        set_tool_failure(order=True, customer=False, history=False)
        with pytest.raises(RuntimeError):
            get_order_details("ORD-1001")
        assert get_customer_account("CUS-001") is not None
        assert get_refund_history("CUS-001") is not None
