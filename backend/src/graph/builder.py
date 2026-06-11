from langgraph.graph import END, START, StateGraph

from graph.assistant_nodes import make_research_assistant_nodes, route_by_state
from graph.assistant_state import ResearchAssistantState
from graph.nodes import make_nodes, paper_select_node
from graph.state import PaperDiscoveryState, PaperSelectState
from services.LlmPaperSelect import LLMJudge
from services.memory_store import MemoryStore
from services.paper_search import PaperSearchService
from services.query_rewriter import QueryRewriter


def build_paper_select_graph():
    builder = StateGraph(PaperSelectState)

    builder.add_node("paper_select", paper_select_node)

    builder.add_edge(START, "paper_select")
    builder.add_edge("paper_select", END)

    return builder.compile()


def build_paper_discovery_graph(
    search_service: PaperSearchService | None = None,
    judge: LLMJudge | None = None,
    memory_store: MemoryStore | None = None,
    query_rewriter: QueryRewriter | None = None,
):
    """
    Graph flow:
    load_memory_context -> rewrite_query -> multi_source_search
    -> dedup_papers -> judge_papers -> rank_papers
    """
    if memory_store is None:
        raise ValueError("memory_store is required")

    nodes = make_nodes(
        search_service=search_service or PaperSearchService(),
        judge=judge or LLMJudge(),
        memory_store=memory_store,
        query_rewriter=query_rewriter or QueryRewriter(),
    )

    builder = StateGraph(PaperDiscoveryState)
    for name, node in nodes.items():
        builder.add_node(name, node)

    builder.add_edge(START, "load_memory_context")
    builder.add_edge("load_memory_context", "rewrite_query")
    builder.add_edge("rewrite_query", "multi_source_search")
    builder.add_edge("multi_source_search", "dedup_papers")
    builder.add_edge("dedup_papers", "judge_papers")
    builder.add_edge("judge_papers", "rank_papers")
    builder.add_edge("rank_papers", END)

    return builder.compile()


def build_research_assistant_graph(
    store,
    discovery_graph,
    knowledge_qa_service,
    idea_service,
):
    nodes = make_research_assistant_nodes(
        store=store,
        discovery_graph=discovery_graph,
        knowledge_qa_service=knowledge_qa_service,
        idea_service=idea_service,
    )

    builder = StateGraph(ResearchAssistantState)
    for name, node in nodes.items():
        builder.add_node(name, node)

    builder.add_edge(START, "load_memory_context")
    builder.add_edge("load_memory_context", "assess_query_coverage")
    builder.add_edge("assess_query_coverage", "route_request")
    builder.add_conditional_edges(
        "route_request",
        route_by_state,
        {
            "basic_explore": "run_basic_explore",
            "advanced_ready": "run_advanced_ready",
            "advanced_search": "run_advanced_search",
            "research_idea": "run_research_idea",
        },
    )
    builder.add_edge("run_basic_explore", "format_assistant_response")
    builder.add_edge("run_advanced_ready", "format_assistant_response")
    builder.add_edge("run_advanced_search", "format_assistant_response")
    builder.add_edge("run_research_idea", "format_assistant_response")
    builder.add_edge("format_assistant_response", END)

    return builder.compile()
