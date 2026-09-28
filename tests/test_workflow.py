"""
Phase 2 integration tests — LangGraph workflow.

Tests cover every routing path through the graph:
  - Auto-approve (low-value, no risk flags)          → COMPLETED
  - Reviewer approval required (standard amount)     → WAITING_FOR_APPROVAL
  - Manager approval required (high-value)           → WAITING_FOR_APPROVAL
  - Escalation (customer/order mismatch)             → ESCALATED
  - Escalation (missing context / tool failure)      → ESCALATED
  - Decline (order not refund-eligible)              → DECLINED
  - Suspicious account (Risk D)                      → WAITING_FOR_APPROVAL (manager)
  - Repeated refunds (Risk A)                        → WAITING_FOR_APPROVAL
  - Missing evidence (Risk C)                        → WAITING_FOR_APPROVAL

Additional tests verify:
  - Audit trail is written to the database
  - Refund state is persisted in the database
  - All 9 nodes are exercised end-to-end
  - LLM decision is present but does NOT control routing
  - Policy engine output controls routing, always
  - Tool failure paths degrade gracefully
"""

from __future__ import annotations

import pytest

from refund_approval_system.agent.graph import build_graph, run_workflow
from refund_approval_system.agent.state import WorkflowState
from refund_approval_system.db.database import init_db
from refund_approval_system.tools.mock_tools import set_tool_failure
from refund_approval_system.models import (
    ApprovalLevel,
    LLMAction,
    RefundRequest,
    RefundStatus,
)
from refund_approval_system.db.repository import get_audit_events, get_refund_state


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _req(
    refund_id: str,
    amount: float,
    customer_id: str = "CUS-001",
    order_id: str = "ORD-1001",
    reason: str = "defective product",
) -> RefundRequest:
    return RefundRequest(
        refund_id=refund_id,
        customer_id=customer_id,
        order_id=order_id,
        amount=amount,
        reason=reason,
    )


@pytest.fixture(autouse=True)
def reset_failures():
    """Always reset mock-tool failure flags between tests."""
    set_tool_failure(order=False, customer=False, history=False)
    yield
    set_tool_failure(order=False, customer=False, history=False)


# --------------------------------------------------------------------------- #
# Path 1: Auto-approve (Rule 1 — low value, no risk flags)                    #
# --------------------------------------------------------------------------- #


class TestAutoApprove:
    """CUS-001 / ORD-1001: active, clean, eligible, evidence present."""

    def test_status_is_completed(self, db_path):
        state = run_workflow(_req("REF-AA-1", 25.0), db_path)
        assert state["status"] == RefundStatus.COMPLETED

    def test_transaction_id_is_set(self, db_path):
        state = run_workflow(_req("REF-AA-2", 25.0), db_path)
        assert state["transaction_id"] is not None
        assert state["transaction_id"].startswith("TXN-")

    def test_policy_result_approval_not_required(self, db_path):
        state = run_workflow(_req("REF-AA-3", 10.0), db_path)
        assert state["policy_result"].approval_required is False

    def test_no_approval_id_created(self, db_path):
        state = run_workflow(_req("REF-AA-4", 10.0), db_path)
        assert state["approval_id"] is None

    def test_risk_flags_empty(self, db_path):
        state = run_workflow(_req("REF-AA-5", 10.0), db_path)
        assert state["policy_result"].risk_flags == []

    def test_llm_decision_present(self, db_path):
        """LLM decision must exist but must NOT be what determined routing."""
        state = run_workflow(_req("REF-AA-6", 10.0), db_path)
        assert state["llm_decision"] is not None
        assert state["llm_decision"].action == LLMAction.REFUND

    def test_audit_trail_written(self, db_path):
        run_workflow(_req("REF-AA-7", 10.0), db_path)
        events = get_audit_events("REF-AA-7", db_path)
        event_types = [e["event_type"] for e in events]
        assert "validate_request" in event_types
        assert "policy_result" in event_types
        assert "refund_completed" in event_types

    def test_state_persisted_in_db(self, db_path):
        run_workflow(_req("REF-AA-8", 10.0), db_path)
        persisted = get_refund_state("REF-AA-8", db_path)
        assert persisted is not None
        assert persisted.status == RefundStatus.COMPLETED

    def test_boundary_just_below_50(self, db_path):
        state = run_workflow(_req("REF-AA-9", 49.99), db_path)
        assert state["status"] == RefundStatus.COMPLETED


# --------------------------------------------------------------------------- #
# Path 2: Reviewer approval (Rule 2 — $50–$500)                               #
# --------------------------------------------------------------------------- #


class TestReviewerApproval:
    def test_status_waiting_for_approval(self, db_path):
        state = run_workflow(_req("REF-REV-1", 150.0), db_path)
        assert state["status"] == RefundStatus.WAITING_FOR_APPROVAL

    def test_approval_level_is_reviewer(self, db_path):
        state = run_workflow(_req("REF-REV-2", 150.0), db_path)
        assert state["policy_result"].approval_level == ApprovalLevel.REVIEWER

    def test_approval_id_is_set(self, db_path):
        state = run_workflow(_req("REF-REV-3", 150.0), db_path)
        assert state["approval_id"] is not None
        assert state["approval_id"].startswith("APR-")

    def test_approval_record_in_db(self, db_path):
        from refund_approval_system.db.repository import get_approval

        state = run_workflow(_req("REF-REV-4", 150.0), db_path)
        row = get_approval(state["approval_id"], db_path)
        assert row is not None
        assert row["required_level"] == "reviewer"
        assert row["status"] == "pending"

    def test_no_transaction_id(self, db_path):
        state = run_workflow(_req("REF-REV-5", 150.0), db_path)
        assert state.get("transaction_id") is None

    def test_exactly_at_50_needs_reviewer(self, db_path):
        state = run_workflow(_req("REF-REV-6", 50.0), db_path)
        assert state["status"] == RefundStatus.WAITING_FOR_APPROVAL
        assert state["policy_result"].approval_level == ApprovalLevel.REVIEWER


# --------------------------------------------------------------------------- #
# Path 3: Manager approval (Rule 3 — > $500)                                  #
# --------------------------------------------------------------------------- #


class TestManagerApproval:
    def test_status_waiting_for_approval(self, db_path):
        state = run_workflow(_req("REF-MGR-1", 800.0), db_path)
        assert state["status"] == RefundStatus.WAITING_FOR_APPROVAL

    def test_approval_level_is_manager(self, db_path):
        state = run_workflow(_req("REF-MGR-2", 800.0), db_path)
        assert state["policy_result"].approval_level == ApprovalLevel.MANAGER

    def test_approval_record_stored_as_manager(self, db_path):
        from refund_approval_system.db.repository import get_approval

        state = run_workflow(
            _req("REF-MGR-3", 900.0, customer_id="CUS-002", order_id="ORD-1002"), db_path
        )
        row = get_approval(state["approval_id"], db_path)
        assert row["required_level"] == "manager"


# --------------------------------------------------------------------------- #
# Path 4: Escalation — customer/order mismatch (Risk B)                       #
# --------------------------------------------------------------------------- #


class TestEscalateMismatch:
    # ORD-1001 belongs to CUS-001; CUS-002 exists but is NOT the owner → mismatch.
    # Using a *known* customer ensures the policy mismatch check fires instead
    # of the earlier missing-context guard.
    _WRONG_CUSTOMER = "CUS-002"
    _ORDER = "ORD-1001"

    def test_status_escalated(self, db_path):
        state = run_workflow(
            _req("REF-ESC-1", 25.0, customer_id=self._WRONG_CUSTOMER, order_id=self._ORDER),
            db_path,
        )
        assert state["status"] == RefundStatus.ESCALATED

    def test_mismatch_risk_flag(self, db_path):
        state = run_workflow(
            _req("REF-ESC-2", 25.0, customer_id=self._WRONG_CUSTOMER, order_id=self._ORDER),
            db_path,
        )
        assert "customer_order_mismatch" in state["policy_result"].risk_flags

    def test_no_transaction_id(self, db_path):
        state = run_workflow(
            _req("REF-ESC-3", 25.0, customer_id=self._WRONG_CUSTOMER, order_id=self._ORDER),
            db_path,
        )
        assert state.get("transaction_id") is None

    def test_escalated_event_in_audit(self, db_path):
        run_workflow(
            _req("REF-ESC-4", 25.0, customer_id=self._WRONG_CUSTOMER, order_id=self._ORDER),
            db_path,
        )
        events = get_audit_events("REF-ESC-4", db_path)
        assert any(e["event_type"] == "escalated" for e in events)


# --------------------------------------------------------------------------- #
# Path 5: Escalation — tool failure (missing context)                         #
# --------------------------------------------------------------------------- #


class TestEscalateToolFailure:
    def test_order_service_failure_escalates(self, db_path):
        set_tool_failure(order=True)
        state = run_workflow(_req("REF-TF-1", 25.0), db_path)
        assert state["status"] == RefundStatus.ESCALATED

    def test_customer_service_failure_escalates(self, db_path):
        set_tool_failure(customer=True)
        state = run_workflow(_req("REF-TF-2", 25.0), db_path)
        assert state["status"] == RefundStatus.ESCALATED

    def test_history_failure_does_not_escalate_alone(self, db_path):
        """Missing history is tolerated — should still auto-approve on low value."""
        set_tool_failure(history=True)
        state = run_workflow(_req("REF-TF-3", 25.0), db_path)
        # Policy still proceeds; history=None means no Risk A trigger
        assert state["status"] == RefundStatus.COMPLETED


# --------------------------------------------------------------------------- #
# Path 6: Decline — order not refund-eligible                                 #
# --------------------------------------------------------------------------- #


class TestDecline:
    def test_status_declined(self, db_path):
        state = run_workflow(
            _req("REF-DEC-1", 50.0, customer_id="CUS-004", order_id="ORD-1004"), db_path
        )
        assert state["status"] == RefundStatus.DECLINED

    def test_declined_risk_flag(self, db_path):
        state = run_workflow(
            _req("REF-DEC-2", 50.0, customer_id="CUS-004", order_id="ORD-1004"), db_path
        )
        assert "order_not_refund_eligible" in state["policy_result"].risk_flags

    def test_no_transaction_id(self, db_path):
        state = run_workflow(
            _req("REF-DEC-3", 50.0, customer_id="CUS-004", order_id="ORD-1004"), db_path
        )
        assert state.get("transaction_id") is None

    def test_declined_event_in_audit(self, db_path):
        run_workflow(
            _req("REF-DEC-4", 50.0, customer_id="CUS-004", order_id="ORD-1004"), db_path
        )
        events = get_audit_events("REF-DEC-4", db_path)
        assert any(e["event_type"] == "declined" for e in events)


# --------------------------------------------------------------------------- #
# Path 7: Suspicious account — Risk D → manager required                      #
# --------------------------------------------------------------------------- #


class TestSuspiciousAccount:
    def test_low_value_suspicious_needs_manager(self, db_path):
        state = run_workflow(
            _req("REF-SUSP-1", 25.0, customer_id="CUS-SUSP", order_id="ORD-SUSP"), db_path
        )
        assert state["status"] == RefundStatus.WAITING_FOR_APPROVAL
        assert state["policy_result"].approval_level == ApprovalLevel.MANAGER

    def test_suspicious_risk_flag_present(self, db_path):
        state = run_workflow(
            _req("REF-SUSP-2", 25.0, customer_id="CUS-SUSP", order_id="ORD-SUSP"), db_path
        )
        assert "suspicious_account_activity" in state["policy_result"].risk_flags


# --------------------------------------------------------------------------- #
# Path 8: Repeated refunds — Risk A → reviewer required                       #
# --------------------------------------------------------------------------- #


class TestRepeatedRefunds:
    def test_low_value_repeat_needs_reviewer(self, db_path):
        state = run_workflow(
            _req("REF-REPT-1", 25.0, customer_id="CUS-REPEAT", order_id="ORD-REPEAT"), db_path
        )
        assert state["status"] == RefundStatus.WAITING_FOR_APPROVAL
        assert state["policy_result"].approval_level == ApprovalLevel.REVIEWER

    def test_repeated_refunds_flag(self, db_path):
        state = run_workflow(
            _req("REF-REPT-2", 25.0, customer_id="CUS-REPEAT", order_id="ORD-REPEAT"), db_path
        )
        assert "repeated_refunds_30d" in state["policy_result"].risk_flags


# --------------------------------------------------------------------------- #
# Path 9: Missing evidence — Risk C → reviewer required                       #
# --------------------------------------------------------------------------- #


class TestMissingEvidence:
    def test_low_value_no_evidence_needs_reviewer(self, db_path):
        state = run_workflow(
            _req("REF-EV-1", 25.0, customer_id="CUS-003", order_id="ORD-1003"), db_path
        )
        assert state["status"] == RefundStatus.WAITING_FOR_APPROVAL
        assert state["policy_result"].approval_level == ApprovalLevel.REVIEWER

    def test_missing_evidence_flag(self, db_path):
        state = run_workflow(
            _req("REF-EV-2", 25.0, customer_id="CUS-003", order_id="ORD-1003"), db_path
        )
        assert "missing_evidence" in state["policy_result"].risk_flags


# --------------------------------------------------------------------------- #
# Structural / graph-topology tests                                            #
# --------------------------------------------------------------------------- #


class TestGraphStructure:
    def test_graph_compiles_without_error(self):
        graph = build_graph()
        assert graph is not None

    def test_all_nodes_have_been_traversed_on_auto_approve(self, db_path):
        """
        For an auto-approve path, audit events must include entries from
        every non-terminal node up to and including execute_refund.
        """
        run_workflow(_req("REF-NODES-1", 10.0), db_path)
        events = get_audit_events("REF-NODES-1", db_path)
        types = {e["event_type"] for e in events}
        assert "validate_request" in types
        assert "llm_recommendation" in types
        assert "policy_result" in types
        assert "refund_completed" in types

    def test_llm_decision_never_directly_controls_routing(self, db_path):
        """
        Even if the LLM would recommend DECLINE, policy must still auto-approve
        a low-value, clean request.  (Stub recommends REFUND here, but the
        invariant is that policy wins regardless.)
        """
        state = run_workflow(_req("REF-NODES-2", 10.0), db_path)
        # Policy says auto-approve → status COMPLETED
        assert state["status"] == RefundStatus.COMPLETED
        # LLM decision is present but did not block execution
        assert state["llm_decision"] is not None

    def test_each_invocation_is_independent(self, db_path):
        """Two different refund IDs must not interfere."""
        s1 = run_workflow(_req("REF-IND-1", 10.0), db_path)
        s2 = run_workflow(_req("REF-IND-2", 200.0), db_path)
        assert s1["status"] == RefundStatus.COMPLETED
        assert s2["status"] == RefundStatus.WAITING_FOR_APPROVAL
        # DB state for each must be independent
        p1 = get_refund_state("REF-IND-1", db_path)
        p2 = get_refund_state("REF-IND-2", db_path)
        assert p1.status == RefundStatus.COMPLETED
        assert p2.status == RefundStatus.WAITING_FOR_APPROVAL

    def test_policy_result_is_always_deterministic(self, db_path):
        """Same request must produce the same policy_result every time."""
        r = _req("REF-DET-1", 200.0)
        s1 = run_workflow(r, db_path)
        r2 = _req("REF-DET-2", 200.0)
        s2 = run_workflow(r2, db_path)
        assert s1["policy_result"].model_dump() == s2["policy_result"].model_dump()


# --------------------------------------------------------------------------- #
# State typing tests                                                           #
# --------------------------------------------------------------------------- #


class TestStateTyping:
    def test_state_has_required_keys_after_run(self, db_path):
        state = run_workflow(_req("REF-TYPE-1", 10.0), db_path)
        assert "request" in state
        assert "status" in state
        assert "policy_result" in state
        assert "llm_decision" in state

    def test_status_is_refund_status_enum(self, db_path):
        state = run_workflow(_req("REF-TYPE-2", 10.0), db_path)
        assert isinstance(state["status"], RefundStatus)

    def test_policy_result_type(self, db_path):
        from refund_approval_system.models import PolicyResult

        state = run_workflow(_req("REF-TYPE-3", 10.0), db_path)
        assert isinstance(state["policy_result"], PolicyResult)

    def test_llm_decision_type(self, db_path):
        from refund_approval_system.models import RefundDecision

        state = run_workflow(_req("REF-TYPE-4", 10.0), db_path)
        assert isinstance(state["llm_decision"], RefundDecision)
