from pydantic import BaseModel


class RefundExecutionResult(BaseModel):
    success: bool
    transaction_id: str | None = None
    error: str | None = None
