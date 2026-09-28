import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
from refund_approval_system.models.enums import LLMAction

load_dotenv(override=True)

class RefundDecision(BaseModel):
    action: LLMAction = Field(..., description="Recommended action")
    amount: float = Field(..., description="Amount the LLM believes should be refunded")
    rationale: str = Field(..., description="LLM explanation for its recommendation")
    confidence: float = Field(..., ge=0.0, le=1.0, description="0-1 confidence score")
    uncertainty: str = Field(..., description="Description of any uncertainties identified")

try:
    api_key = os.getenv("GROQ_API_KEY")
    model = ChatGroq(
        model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        temperature=0,
        api_key=api_key
    )
    structured = model.with_structured_output(RefundDecision)
    print("Success setting up structured output!")
    
    result = structured.invoke("Test refund decision for $100")
    print(result)
except Exception as e:
    import traceback
    traceback.print_exc()
