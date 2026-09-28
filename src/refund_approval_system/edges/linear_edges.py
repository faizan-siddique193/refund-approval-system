# edges/linear_edges.py
from langgraph.graph import START, StateGraph


def add_linear_edges(graph: StateGraph) -> None:
    """
    Add all deterministic sequential edges.
    These never branch -- always follow this order.
    """
    graph.add_edge(START, "validate_request")
    graph.add_edge("validate_request", "retrieve_context")
    graph.add_edge("retrieve_context", "analyze_case")
    graph.add_edge("analyze_case", "policy_check")
    graph.add_edge("create_approval", "process_approval")
