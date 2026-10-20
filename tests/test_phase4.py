import pytest
from langgraph.checkpoint.memory import MemorySaver

from refund_approval_system.agent.graph import build_graph, run_workflow
from refund_approval_system.agent.state import WorkflowState
from refund_approval_system.models import (
    ApprovalLevel,
    ApprovalResult,
    ApprovalStatus,
    RefundRequest,
    RefundStatus,
)
from refund_approval_system.db.repository import get_approval, update_approval_decision

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

class TestPhase4PauseResume:
    def test_pause_at_process_approval(self, db_path):
        checkpointer = MemorySaver()
        graph = build_graph(checkpointer=checkpointer)
        
        request = _req("REF-PH4-1", 150.0) # Reviewer approval required
        initial_state = {
            "request": request,
            "db_path": db_path,
            "status": RefundStatus.RECEIVED,
        }
        
        config = {"configurable": {"thread_id": "thread-1"}}
        final_state = graph.invoke(initial_state, config)
        
        assert final_state["status"] == RefundStatus.WAITING_FOR_APPROVAL
        assert final_state["approval_id"] is not None
        assert final_state.get("transaction_id") is None
        
        # Verify graph is paused at process_approval
        state_snapshot = graph.get_state(config)
        assert state_snapshot.next == ("process_approval",)
        
        # Resume with Approval
        approval_result = ApprovalResult(
            approval_id=final_state["approval_id"],
            decision=ApprovalStatus.APPROVED,
            reviewer_id="REV-01",
            reviewer_role=ApprovalLevel.REVIEWER,
            refund_id=request.refund_id,
            order_id=request.order_id,
            amount=request.amount,
        )
        
        graph.update_state(config, {"approval_result": approval_result})
        final_state_resumed = graph.invoke(None, config)
        assert final_state_resumed["status"] == RefundStatus.COMPLETED
        assert final_state_resumed.get("transaction_id") is not None

    def test_resume_with_rejection(self, db_path):
        checkpointer = MemorySaver()
        graph = build_graph(checkpointer=checkpointer)
        
        request = _req("REF-PH4-2", 150.0)
        config = {"configurable": {"thread_id": "thread-2"}}
        initial_state = {"request": request, "db_path": db_path, "status": RefundStatus.RECEIVED}
        state = graph.invoke(initial_state, config)
        
        approval_result = ApprovalResult(
            approval_id=state["approval_id"],
            decision=ApprovalStatus.REJECTED,
            reviewer_id="REV-01",
            reviewer_role=ApprovalLevel.REVIEWER,
            refund_id=request.refund_id,
            order_id=request.order_id,
            amount=request.amount,
        )
        
        graph.update_state(config, {"approval_result": approval_result})
        state_resumed = graph.invoke(None, config)
        assert state_resumed["status"] == RefundStatus.REJECTED
        assert state_resumed.get("transaction_id") is None

    def test_invalid_authority(self, db_path):
        checkpointer = MemorySaver()
        graph = build_graph(checkpointer=checkpointer)
        
        request = _req("REF-PH4-3", 800.0) # Manager required
        config = {"configurable": {"thread_id": "thread-3"}}
        initial_state = {"request": request, "db_path": db_path, "status": RefundStatus.RECEIVED}
        state = graph.invoke(initial_state, config)
        
        # Try to approve with REVIEWER role
        approval_result = ApprovalResult(
            approval_id=state["approval_id"],
            decision=ApprovalStatus.APPROVED,
            reviewer_id="REV-01",
            reviewer_role=ApprovalLevel.REVIEWER,
            refund_id=request.refund_id,
            order_id=request.order_id,
            amount=request.amount,
        )
        
        graph.update_state(config, {"approval_result": approval_result})
        state_resumed = graph.invoke(None, config)
        assert state_resumed["status"] == RefundStatus.FAILED
        assert "Insufficient approval authority" in state_resumed["error"]

    def test_invalid_binding_wrong_amount(self, db_path):
        checkpointer = MemorySaver()
        graph = build_graph(checkpointer=checkpointer)
        
        request = _req("REF-PH4-4", 150.0)
        config = {"configurable": {"thread_id": "thread-4"}}
        initial_state = {"request": request, "db_path": db_path, "status": RefundStatus.RECEIVED}
        state = graph.invoke(initial_state, config)
        
        approval_result = ApprovalResult(
            approval_id=state["approval_id"],
            decision=ApprovalStatus.APPROVED,
            reviewer_id="REV-01",
            reviewer_role=ApprovalLevel.REVIEWER,
            refund_id=request.refund_id,
            order_id=request.order_id,
            amount=100.0, # Wrong amount
        )
        
        graph.update_state(config, {"approval_result": approval_result})
        state_resumed = graph.invoke(None, config)
        assert state_resumed["status"] == RefundStatus.FAILED
        assert "Amount mismatch" in state_resumed["error"]

    def test_expired_approval(self, db_path):
        checkpointer = MemorySaver()
        graph = build_graph(checkpointer=checkpointer)
        
        request = _req("REF-PH4-5", 150.0)
        config = {"configurable": {"thread_id": "thread-5"}}
        initial_state = {"request": request, "db_path": db_path, "status": RefundStatus.RECEIVED}
        state = graph.invoke(initial_state, config)
        
        # Manually expire the approval in the database
        update_approval_decision(state["approval_id"], ApprovalStatus.EXPIRED, "SYSTEM", db_path)
        
        approval_result = ApprovalResult(
            approval_id=state["approval_id"],
            decision=ApprovalStatus.APPROVED,
            reviewer_id="REV-01",
            reviewer_role=ApprovalLevel.REVIEWER,
            refund_id=request.refund_id,
            order_id=request.order_id,
            amount=request.amount,
        )
        
        graph.update_state(config, {"approval_result": approval_result})
        state_resumed = graph.invoke(None, config)
        assert state_resumed["status"] == RefundStatus.FAILED
        assert "Approval is not pending" in state_resumed["error"]

    def test_automatic_time_based_expiry(self, db_path):
        from datetime import datetime, timedelta, timezone
        from refund_approval_system.db.database import get_connection
        from refund_approval_system.db.repository import get_approval

        checkpointer = MemorySaver()
        graph = build_graph(checkpointer=checkpointer)

        request = _req("REF-PH4-AUTO-EXP", 150.0)
        config = {"configurable": {"thread_id": "thread-auto-exp"}}
        initial_state = {"request": request, "db_path": db_path, "status": RefundStatus.RECEIVED}
        state = graph.invoke(initial_state, config)

        # Backdate expires_at to 1 hour in the past
        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")
        with get_connection(db_path) as conn:
            conn.execute(
                "UPDATE approvals SET expires_at = ? WHERE approval_id = ?",
                (past_time, state["approval_id"]),
            )

        approval_result = ApprovalResult(
            approval_id=state["approval_id"],
            decision=ApprovalStatus.APPROVED,
            reviewer_id="REV-01",
            reviewer_role=ApprovalLevel.REVIEWER,
            refund_id=request.refund_id,
            order_id=request.order_id,
            amount=request.amount,
        )

        graph.update_state(config, {"approval_result": approval_result})
        state_resumed = graph.invoke(None, config)
        assert state_resumed["status"] == RefundStatus.FAILED
        assert "expired" in state_resumed["error"].lower()

        # Verify DB status transitioned to expired
        db_record = get_approval(state["approval_id"], db_path)
        assert db_record["status"] == ApprovalStatus.EXPIRED.value

    def test_caller_self_declared_manager_role_rejected(self, db_path):
        checkpointer = MemorySaver()
        graph = build_graph(checkpointer=checkpointer)

        request = _req("REF-PH4-SPOOF", 800.0)  # Requires Manager
        config = {"configurable": {"thread_id": "thread-spoof"}}
        initial_state = {"request": request, "db_path": db_path, "status": RefundStatus.RECEIVED}
        state = graph.invoke(initial_state, config)

        # Caller attempts to self-declare as MANAGER with a REVIEWER id
        approval_result = ApprovalResult(
            approval_id=state["approval_id"],
            decision=ApprovalStatus.APPROVED,
            reviewer_id="REV-01",
            reviewer_role=ApprovalLevel.MANAGER,  # Caller self-declaration
            refund_id=request.refund_id,
            order_id=request.order_id,
            amount=request.amount,
        )

        graph.update_state(config, {"approval_result": approval_result})
        state_resumed = graph.invoke(None, config)
        assert state_resumed["status"] == RefundStatus.FAILED
        assert "Unauthorized role escalation" in state_resumed["error"]

    def test_authorized_manager_approval_succeeds(self, db_path):
        checkpointer = MemorySaver()
        graph = build_graph(checkpointer=checkpointer)

        request = _req("REF-PH4-MGR-OK", 800.0)  # Requires Manager
        config = {"configurable": {"thread_id": "thread-mgr-ok"}}
        initial_state = {"request": request, "db_path": db_path, "status": RefundStatus.RECEIVED}
        state = graph.invoke(initial_state, config)

        # Authorized manager submits approval
        approval_result = ApprovalResult(
            approval_id=state["approval_id"],
            decision=ApprovalStatus.APPROVED,
            reviewer_id="MGR-01",
            reviewer_role=ApprovalLevel.MANAGER,
            refund_id=request.refund_id,
            order_id=request.order_id,
            amount=request.amount,
        )

        graph.update_state(config, {"approval_result": approval_result})
        state_resumed = graph.invoke(None, config)
        assert state_resumed["status"] == RefundStatus.COMPLETED
        assert state_resumed.get("transaction_id") is not None

