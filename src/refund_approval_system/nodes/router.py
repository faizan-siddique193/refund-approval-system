import logging
from refund_approval_system.agent.state import WorkflowState
from refund_approval_system.models import RefundStatus, LLMAction

logger = logging.getLogger(__name__)

def route_action(state: WorkflowState) -> str:
    policy = state.get("policy_result")
    if policy is None:
        logger.error("route_action: no policy_result in state — routing to failed")
        return "failed"

    if policy.allowed_action == LLMAction.ESCALATE:
        logger.info("route_action → escalate")
        return "escalate"

    if policy.allowed_action == LLMAction.DECLINE:
        logger.info("route_action → decline")
        return "decline"

    if policy.approval_required:
        logger.info("route_action → create_approval (level=%s)", policy.approval_level)
        return "create_approval"

    llm_decision = state.get("llm_decision")
    if llm_decision and llm_decision.action == LLMAction.REQUEST_INFORMATION:
        logger.info("route_action → needs_information (LLM requested more info)")
        return "needs_information"

    if policy.approval_required:
        logger.info("route_action → create_approval (level=%s)", policy.approval_level)
        return "create_approval"

    logger.info("route_action → execute_refund (auto-approve)")
    return "execute_refund"

def route_approval(state: WorkflowState) -> str:
    status = state.get("status")
    if status == RefundStatus.APPROVED:
        return "execute_refund"
    elif status == RefundStatus.REJECTED:
        return "reject_refund"
    else:
        return "failed"
