from pydantic import BaseModel, Field

from refund_approval_system.models.enums import ApprovalLevel, RefundStatus


class RefundResponse(BaseModel):
    refund_id: str
    status: RefundStatus
    action: str | None = None
    amount: float
    rationale: str | None = None
    approval_required: bool = False
    approval_id: str | None = None
    approval_level: ApprovalLevel | None = None
    risk_flags: list[str] = Field(default_factory=list)
    transaction_id: str | None = None
    error: str | None = None
