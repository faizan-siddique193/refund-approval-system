from pydantic import BaseModel, Field

from refund_approval_system.models.enums import ApprovalLevel, LLMAction


class PolicyResult(BaseModel):
    allowed_action: LLMAction = Field(..., description="Action the policy permits")
    approval_required: bool = Field(
        ..., description="Whether human approval is required"
    )
    approval_level: ApprovalLevel | None = Field(
        None, description="Required approval tier (if approval_required)"
    )
    risk_flags: list[str] = Field(
        default_factory=list, description="Risk conditions detected"
    )
    reason: str = Field(
        ..., description="Plain-language explanation of the policy decision"
    )
