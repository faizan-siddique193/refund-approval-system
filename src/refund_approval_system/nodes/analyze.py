import logging
from refund_approval_system.agent.state import WorkflowState
from refund_approval_system.models import RefundRequest, RefundStatus
from refund_approval_system.agent.llm import analyze_with_llm
from refund_approval_system.nodes.helpers import _audit, _snapshot

logger = logging.getLogger(__name__)

def analyze_case(state: WorkflowState) -> dict:
    request: RefundRequest = state["request"]
    logger.info("analyze_case: LLM analysis for refund %s", request.refund_id)
    _audit(state, "analyze_case", "Running LLM analysis")
    _snapshot(state, RefundStatus.ANALYZING)

    llm_decision = analyze_with_llm(
        request=request,
        order=state.get("order"),
        customer=state.get("customer"),
        history=state.get("history"),
    )

    logger.info(
        "analyze_case: LLM recommends action=%s confidence=%.2f",
        llm_decision.action,
        llm_decision.confidence,
    )
    _audit(
        state,
        "llm_recommendation",
        f"action={llm_decision.action.value} confidence={llm_decision.confidence:.2f}",
    )

    return {
        "llm_decision": llm_decision,
        "status": RefundStatus.ANALYZING,
    }
