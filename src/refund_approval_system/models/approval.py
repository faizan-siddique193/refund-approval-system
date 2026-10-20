from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from refund_approval_system.models.enums import ApprovalLevel, ApprovalStatus

DEFAULT_APPROVAL_EXPIRY_HOURS = 24


class ApprovalRequest(BaseModel):
    approval_id: str
    refund_id: str
    order_id: str
    amount: float
    required_level: ApprovalLevel
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=DEFAULT_APPROVAL_EXPIRY_HOURS)
    )


class ApprovalResult(BaseModel):
    approval_id: str
    decision: ApprovalStatus  # approved | rejected only (expired set by system)
    reviewer_id: str
    reviewer_role: ApprovalLevel
    refund_id: str
    order_id: str
    amount: float
