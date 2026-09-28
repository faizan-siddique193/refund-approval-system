# edges/conditional_edges.py
from langgraph.graph import StateGraph
from refund_approval_system.nodes import route_action, route_approval


def add_conditional_edges(graph: StateGraph) -> None:
    """
    Add all branching edges driven by router functions.
    These decide the next node based on workflow state.
    """
    # after policy check -- main routing
    graph.add_conditional_edges(
        "policy_check",
        route_action,
        {
            "execute_refund": "execute_refund",
            "create_approval": "create_approval",
            "escalate": "escalate",
            "decline": "decline",
            "failed": "failed",
            "needs_information": "needs_information",
        },
    )

    # after approval processing -- approval routing
    graph.add_conditional_edges(
        "process_approval",
        route_approval,
        {
            "execute_refund": "execute_refund",
            "reject_refund": "reject_refund",
            "failed": "failed",
        },
    )
