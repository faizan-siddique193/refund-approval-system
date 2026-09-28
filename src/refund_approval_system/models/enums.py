from enum import Enum


class RefundStatus(str, Enum):
    RECEIVED = "received"
    VALIDATING = "validating"
    RETRIEVING_CONTEXT = "retrieving_context"
    ANALYZING = "analyzing"
    POLICY_CHECK = "policy_check"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"
    NEEDS_INFORMATION = "needs_information"
    DECLINED = "declined"


class LLMAction(str, Enum):
    REFUND = "refund"
    REQUEST_INFORMATION = "request_information"
    ESCALATE = "escalate"
    DECLINE = "decline"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalLevel(str, Enum):
    REVIEWER = "reviewer"
    MANAGER = "manager"
