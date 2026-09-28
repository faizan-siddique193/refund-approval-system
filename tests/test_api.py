import os
import pytest
from fastapi.testclient import TestClient

from refund_approval_system.api import app
from refund_approval_system.db.database import init_db
from refund_approval_system.models import ApprovalLevel, ApprovalStatus, RefundStatus

@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "test_api.db")
    os.environ["DATABASE_PATH"] = db_path
    init_db(db_path)
    with TestClient(app) as client:
        yield client

def test_submit_refund(client):
    response = client.post("/refunds", json={
        "refund_id": "API-1",
        "customer_id": "CUS-001",
        "order_id": "ORD-1001",
        "amount": 25.0,
        "reason": "broken"
    })
    assert response.status_code == 202
    data = response.json()
    assert data["refund_id"] == "API-1"
    assert data["status"] == RefundStatus.COMPLETED.value
    assert data["transaction_id"] is not None

def test_submit_duplicate_refund(client):
    req = {
        "refund_id": "API-DUP",
        "customer_id": "CUS-001",
        "order_id": "ORD-1001",
        "amount": 25.0,
        "reason": "broken"
    }
    client.post("/refunds", json=req)
    response = client.post("/refunds", json=req)
    assert response.status_code == 409

def test_get_refund(client):
    req = {
        "refund_id": "API-GET",
        "customer_id": "CUS-001",
        "order_id": "ORD-1001",
        "amount": 25.0,
        "reason": "broken"
    }
    client.post("/refunds", json=req)
    response = client.get("/refunds/API-GET")
    assert response.status_code == 200
    assert response.json()["refund_id"] == "API-GET"

def test_get_refund_not_found(client):
    response = client.get("/refunds/NONEXISTENT")
    assert response.status_code == 404

def test_submit_approval(client):
    # Needs reviewer approval
    req = {
        "refund_id": "API-APP",
        "customer_id": "CUS-001",
        "order_id": "ORD-1001",
        "amount": 150.0, 
        "reason": "broken"
    }
    resp1 = client.post("/refunds", json=req)
    assert resp1.status_code == 202
    data1 = resp1.json()
    assert data1["status"] == RefundStatus.WAITING_FOR_APPROVAL.value
    approval_id = data1["approval_id"]
    
    # Submit approval
    approval_req = {
        "approval_id": approval_id,
        "decision": ApprovalStatus.APPROVED.value,
        "reviewer_id": "REV-1",
        "reviewer_role": ApprovalLevel.REVIEWER.value,
        "refund_id": "API-APP",
        "order_id": "ORD-1001",
        "amount": 150.0
    }
    resp2 = client.post(f"/approvals/{approval_id}", json=approval_req)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == RefundStatus.COMPLETED.value
    assert data2["transaction_id"] is not None

def test_submit_approval_mismatch(client):
    response = client.post("/approvals/APP-123", json={
        "approval_id": "APP-999",
        "decision": ApprovalStatus.APPROVED.value,
        "reviewer_id": "REV-1",
        "reviewer_role": ApprovalLevel.REVIEWER.value,
        "refund_id": "API-APP",
        "order_id": "ORD-1001",
        "amount": 150.0
    })
    assert response.status_code == 400

def test_get_audit(client):
    req = {
        "refund_id": "API-AUD",
        "customer_id": "CUS-001",
        "order_id": "ORD-1001",
        "amount": 25.0,
        "reason": "broken"
    }
    client.post("/refunds", json=req)
    response = client.get("/refunds/API-AUD/audit")
    assert response.status_code == 200
    events = response.json()
    assert len(events) > 0
    assert any(e["event_type"] == "refund_completed" for e in events)

def test_get_audit_not_found(client):
    response = client.get("/refunds/NONEXISTENT/audit")
    assert response.status_code == 404
