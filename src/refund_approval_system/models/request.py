from pydantic import BaseModel, Field, field_validator


class RefundRequest(BaseModel):
    refund_id: str = Field(..., description="Unique identifier for this refund request")
    customer_id: str = Field(..., description="Customer submitting the request")
    order_id: str = Field(..., description="Order being refunded")
    amount: float = Field(..., gt=0, description="Refund amount -- must be positive")
    reason: str = Field(..., description="Customer-provided reason for the refund")

    # run validator at the time of initialization
    @field_validator("refund_id", "customer_id", "order_id", "reason")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Field must not be blank")
        return value.strip()
