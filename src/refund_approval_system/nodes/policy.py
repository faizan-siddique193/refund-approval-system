import logging
from refund_approval_system.agent.state import WorkflowState
from refund_approval_system.models import RefundRequest, RefundStatus
from refund_approval_system.policy import evaluate_policy
from refund_approval_system.nodes.helpers import _audit, _snapshot

logger = logging.getLogger(__name__)

def policy_check(state: WorkflowState) -> dict:
    request: RefundRequest = state["request"]
    logger.info("policy_check: evaluating policy for refund %s", request.refund_id)
    _audit(state, "policy_check", "Running deterministic policy engine")
    _snapshot(state, RefundStatus.POLICY_CHECK)

    policy_result = evaluate_policy(
        request=request,
        order=state.get("order"),
        customer=state.get("customer"),
        history=state.get("history"),
    )

    logger.info(
        "policy_check: action=%s approval_required=%s level=%s flags=%s",
        policy_result.allowed_action,
        policy_result.approval_required,
        policy_result.approval_level,
        policy_result.risk_flags,
    )
    _audit(
        state,
        "policy_result",
        (
            f"action={policy_result.allowed_action.value} "
            f"approval_required={policy_result.approval_required} "
            f"flags={policy_result.risk_flags}"
        ),
    )

    return {
        "policy_result": policy_result,
        "status": RefundStatus.POLICY_CHECK,
    }
