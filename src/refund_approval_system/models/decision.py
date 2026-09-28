from pydantic import BaseModel, Field

from refund_approval_system.models.enums import LLMAction


class RefundDecision(BaseModel):
    action: LLMAction = Field(..., description="Recommended action")
    amount: float = Field(..., description="Amount the LLM believes should be refunded")
    rationale: str = Field(..., description="LLM explanation for its recommendation")
    confidence: float = Field(..., ge=0.0, le=1.0, description="0-1 confidence score")
    uncertainty: str = Field(
        ..., description="Description of any uncertainties identified"
    )
