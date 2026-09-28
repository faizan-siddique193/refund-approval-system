"""
LLM integration layer — advisory only.

The real LLM is gated behind the GROQ_API_KEY environment variable.
When the key is absent or invalid, a ValueError is raised with a clear message.

This file is the only place that touches the LLM. Nodes call
analyze_with_llm and receive a RefundDecision. The policy engine
ignores the LLM output entirely -- it is advisory only.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq

from refund_approval_system.models import (
    CustomerContext,
    LLMAction,
    OrderContext,
    RefundDecision,
    RefundHistory,
    RefundRequest,
)

logger = logging.getLogger(__name__)

# load once at module level -- not inside a function
load_dotenv(override=True)


def analyze_with_llm(
    request: RefundRequest,
    order: OrderContext | None,
    customer: CustomerContext | None,
    history: RefundHistory | None,
) -> RefundDecision:

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        logger.warning("GROQ_API_KEY not found")
        raise ValueError("GROQ_API_KEY not found")

    elif not api_key.startswith("gsk_"):
        logger.warning("Invalid GROQ_API_KEY format")
        raise ValueError("Invalid GROQ_API_KEY")

    else:
        logger.info("Using Groq LLM for refund %s", request.refund_id)
        return _real_llm_analyze(request, order, customer, history, api_key)


def _real_llm_analyze(
    request: RefundRequest,
    order: OrderContext | None,
    customer: CustomerContext | None,
    history: RefundHistory | None,
    api_key: str,  # passed explicitly from analyze_with_llm
) -> RefundDecision:
    """
    Call the real LLM via LangChain and parse structured output.

    Kept separate so it can be unit-tested independently,
    and so the fallback path is never accidentally affected.
    """
    try:
        from refund_approval_system.prompts.analyze import get_analyze_prompt

        model = ChatGroq(
            model=os.getenv("LLM_MODEL", "llama-3.1-70b-versatile"),
            temperature=0,
            api_key=api_key,  # explicit, no ambiguity
        )

        structured = model.with_structured_output(RefundDecision)
        prompt = get_analyze_prompt()
        chain = prompt | structured

        result = chain.invoke(
            {
                "request": request.model_dump_json(),
                "order": order.model_dump_json() if order else "unavailable",
                "customer": customer.model_dump_json() if customer else "unavailable",
                "history": history.model_dump_json() if history else "unavailable",
            }
        )

        logger.info("LLM recommendation for %s: %s", request.refund_id, result.action)
        return result

    except Exception as exc:
        logger.error(
            "LLM call failed for %s: %s — falling back to safe escalation",
            request.refund_id,
            exc,
        )
        # safe fallback -- never return None
        return RefundDecision(
            action=LLMAction.ESCALATE,
            amount=request.amount,
            rationale=f"LLM unavailable, escalating for safety: {exc}",
            confidence=0.0,
            uncertainty="API request failed",
        )
