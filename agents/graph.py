from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agents.analyzer import analyzer_node
from agents.planner import planner_node
from agents.publisher import publisher_node
from agents.researcher import researcher_node
from agents.state import SynState
from agents.writer import writer_node


def build_graph():
    graph = StateGraph(SynState)

    graph.add_node("planner", planner_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("analyzer", analyzer_node)
    graph.add_node("writer", writer_node)
    graph.add_node("publisher", publisher_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "researcher")
    graph.add_edge("researcher", "analyzer")
    graph.add_edge("analyzer", "writer")
    graph.add_edge("writer", "publisher")
    graph.add_edge("publisher", END)

    # MemorySaver pour fault-tolerance intra-run.
    # La persistance inter-runs est assurée manuellement dans publisher.py via Redis.
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
