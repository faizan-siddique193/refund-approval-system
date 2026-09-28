# edges/terminal_edges.py
from langgraph.graph import END, StateGraph


def add_terminal_edges(graph: StateGraph) -> None:
    """
    Add all edges that lead to END.
    These are final states -- no further processing.
    """
    terminal_nodes = [
        "execute_refund",
        "escalate",
        "decline",
        "reject_refund",
        "needs_information",
        "failed",
    ]

    for node in terminal_nodes:
        graph.add_edge(node, END)
