# graph.py
from langgraph.graph import StateGraph

from refund_approval_system.agent.state import WorkflowState
from refund_approval_system.edges import (
    add_conditional_edges,
    add_linear_edges,
    add_terminal_edges,
)
from refund_approval_system.nodes import (
    analyze_case,
    create_approval,
    decline,
    escalate,
    execute_refund,
    failed,
    needs_information,
    policy_check,
    process_approval,
    reject_refund,
    retrieve_context,
    validate_request,
)


def build_graph(checkpointer=None):

    graph = StateGraph(WorkflowState)

    # register nodes
    graph.add_node("validate_request", validate_request)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("analyze_case", analyze_case)
    graph.add_node("policy_check", policy_check)
    graph.add_node("create_approval", create_approval)
    graph.add_node("execute_refund", execute_refund)
    graph.add_node("escalate", escalate)
    graph.add_node("decline", decline)
    graph.add_node("failed", failed)
    graph.add_node("process_approval", process_approval)
    graph.add_node("reject_refund", reject_refund)
    graph.add_node("needs_information", needs_information)

    # add edges
    add_linear_edges(graph)
    add_conditional_edges(graph)
    add_terminal_edges(graph)

    return graph.compile(
        checkpointer=checkpointer, interrupt_before=["process_approval"]
    )
