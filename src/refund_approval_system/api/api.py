import os

from fastapi import FastAPI, HTTPException, status
from langgraph.checkpoint.memory import MemorySaver
from refund_approval_system.agent.graph import build_graph
from refund_approval_system.db import init_db
from refund_approval_system.db.repository import get_audit_events, get_refund_state
from refund_approval_system.models import (
    ApprovalResult,
    AuditEvent,
    RefundRequest,
    RefundResponse,
    RefundStatus,
)

app = FastAPI(title="Refund Approval API")

# Use a global checkpointer for the API lifecycle
checkpointer = MemorySaver()
graph = build_graph(checkpointer=checkpointer)


def get_db_path() -> str:
    return os.environ.get("DATABASE_PATH", "refund_approval.db")


@app.on_event("startup")
def startup():
    init_db(get_db_path())


@app.post(
    "/refunds", response_model=RefundResponse, status_code=status.HTTP_202_ACCEPTED
)
def submit_refund(request: RefundRequest):
    db_path = get_db_path()
    existing = get_refund_state(request.refund_id, db_path)
    if existing:
        raise HTTPException(status_code=409, detail="Refund ID already exists.")

    config = {"configurable": {"thread_id": request.refund_id}}
    initial_state = {
        "request": request,
        "db_path": db_path,
        "status": RefundStatus.RECEIVED,
    }

    graph.invoke(initial_state, config)

    state_in_db = get_refund_state(request.refund_id, db_path)
    if not state_in_db:
        raise HTTPException(status_code=500, detail="Failed to save refund state.")
    return state_in_db


@app.get("/refunds/{refund_id}", response_model=RefundResponse)
def get_refund(refund_id: str):
    db_path = get_db_path()
    state = get_refund_state(refund_id, db_path)
    if not state:
        raise HTTPException(status_code=404, detail="Refund not found.")
    return state


@app.post("/approvals/{approval_id}", response_model=RefundResponse)
def submit_approval(approval_id: str, result: ApprovalResult):
    if result.approval_id != approval_id:
        raise HTTPException(
            status_code=400, detail="Approval ID in path and body do not match."
        )

    thread_id = result.refund_id
    config = {"configurable": {"thread_id": thread_id}}

    state = graph.get_state(config)
    if not state or not state.next or "process_approval" not in state.next:
        raise HTTPException(
            status_code=400, detail="Workflow is not waiting for approval."
        )

    graph.update_state(config, {"approval_result": result})
    graph.invoke(None, config)

    db_path = get_db_path()
    updated_state = get_refund_state(result.refund_id, db_path)
    return updated_state


@app.get("/refunds/{refund_id}/audit", response_model=list[AuditEvent])
def get_audit(refund_id: str):
    db_path = get_db_path()
    events = get_audit_events(refund_id, db_path)
    if not events:
        raise HTTPException(status_code=404, detail="No audit events found.")
    return events
