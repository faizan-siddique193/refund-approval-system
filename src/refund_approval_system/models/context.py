from pydantic import BaseModel


class OrderContext(BaseModel):
    order_id: str
    customer_id: str
    order_total: float
    delivered: bool
    refund_eligible: bool
    evidence_present: bool


class CustomerContext(BaseModel):
    customer_id: str
    account_status: str  # e.g. "active", "suspended", "closed"
    suspicious_activity: bool


class RefundHistory(BaseModel):
    customer_id: str
    refund_count_30d: int
    total_refunded_30d: float
