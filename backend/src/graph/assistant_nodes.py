from __future__ import annotations

from services.coverage import calculate_coverage_score
from services.idea_service import IdeaServiceError
from services.qa_service import QAServiceError
from services.retrieval_service import RetrievalServiceError
from services.schemas import ResearchDiscoverySection, ResearchKnowledgeSection


ADVANCED_THRESHOLD = 0.5


def make_research_assistant_nodes(
    store,
    discovery_graph,
    knowledge_qa_service,
    idea_service,
):
    def load_memory_context(state: dict) -> dict:
        return {"memory_context": store.build_memory_context()}

    def assess_query_coverage(state: dict) -> dict:
        errors = state["errors"]
        try:
            retrieval_response = knowledge_qa_service.retrieval_service.search(state["query"], top_k=state["top_k"])
            has_sources = bool(retrieval_response.results)
        except RetrievalServiceError as exc:
            has_sources = False
            errors = errors + [{"section": "coverage", "message": exc.detail}]
        score, reason = calculate_coverage_score(
            query=state["query"],
            semantic_memory_text=_semantic_memory_text(state["memory_context"]),
            recent_log_text=_recent_log_text(state["memory_context"]),
            has_knowledge_sources=has_sources,
        )
        updates = {
            "coverage_score": score,
            "route_reason": reason,
            "errors": errors,
        }
        return updates

    def route_request(state: dict) -> dict:
        intent = state["intent"]
        if intent == "research":
            return {"mode": "advanced", "route": "research_idea"}
        if intent == "search":
            return {"mode": "advanced", "route": "advanced_search"}
        if state["coverage_score"] >= ADVANCED_THRESHOLD:
            return {"mode": "advanced", "route": "advanced_ready"}
        return {"mode": "basic", "route": "basic_explore"}

    def run_basic_explore(state: dict) -> dict:
        discovery, errors = _run_discovery(discovery_graph, state, enabled=True)
        knowledge, knowledge_errors = _knowledge_from_state_or_service(knowledge_qa_service, state, enabled=True)
        errors.extend(knowledge_errors)
        return {
            "discovery": discovery.model_dump(),
            "knowledge": knowledge.model_dump(),
            "assistant_message": (
                "This looks like a new or lightly covered research area. I recommended top papers "
                "and checked the local knowledge base. Select useful candidates and upload PDFs to "
                "improve later research assistance."
            ),
            "next_action": {
                "type": "upload_pdf",
                "options": ["review_candidates", "upload_pdf"],
                "message": "Review the recommended papers and upload PDFs for the ones you want to keep.",
            },
            "suggested_user_actions": [
                "Review the recommended discovery candidates.",
                "Accept useful papers and upload PDFs.",
                "Run embedding after upload so future answers can cite local chunks.",
            ],
            "errors": state["errors"] + errors,
        }

    def run_advanced_ready(state: dict) -> dict:
        return {
            "discovery": ResearchDiscoverySection(enabled=False).model_dump(),
            "knowledge": ResearchKnowledgeSection(enabled=False).model_dump(),
            "assistant_message": (
                "This query appears related to your existing research context. Do you have a new "
                "experiment log to analyze, or should I continue with contextual search?"
            ),
            "next_action": {
                "type": "choose_intent",
                "options": ["research", "search"],
                "message": "Choose research if you have a structured experiment log; choose search for contextual papers and answers.",
            },
            "suggested_user_actions": [
                "Submit a structured experiment log for idea recommendations.",
                "Continue with search for contextual paper recommendations and knowledge-base answers.",
            ],
        }

    def run_advanced_search(state: dict) -> dict:
        discovery, errors = _run_discovery(discovery_graph, state, enabled=True)
        knowledge, knowledge_errors = _knowledge_from_state_or_service(knowledge_qa_service, state, enabled=True)
        errors.extend(knowledge_errors)
        return {
            "discovery": discovery.model_dump(),
            "knowledge": knowledge.model_dump(),
            "assistant_message": (
                "I used your existing research context to run contextual discovery and local knowledge answering."
            ),
            "next_action": {
                "type": "none",
                "options": [],
                "message": "You can accept papers, upload PDFs, or submit an experiment log next.",
            },
            "suggested_user_actions": [
                "Review contextual discovery candidates.",
                "Use knowledge sources as grounded evidence.",
                "Submit an experiment log if you want idea recommendations.",
            ],
            "errors": state["errors"] + errors,
        }

    def run_research_idea(state: dict) -> dict:
        experiment_log = state["experiment_log"]
        if experiment_log is None:
            return {
                "errors": state["errors"] + [{"section": "idea", "message": "experiment_log is required for research intent"}]
            }
        try:
            response = idea_service.recommend(
                experiment_log=experiment_log,
                save_log=state["save_log"],
                include_discovery=state["include_discovery"],
                top_k=state["top_k"],
                idea_count=state["idea_count"],
            )
        except IdeaServiceError as exc:
            return {
                "ideas": [],
                "assistant_message": "I could not generate idea recommendations from this experiment log.",
                "errors": state["errors"] + [{"section": "idea", "message": exc.detail}],
            }
        return {
            "discovery": ResearchDiscoverySection(
                enabled=response.discovery.enabled,
                candidates=response.discovery.candidates,
                error=response.discovery.error,
            ).model_dump(),
            "knowledge": ResearchKnowledgeSection(
                enabled=True,
                answer=None,
                sources=response.knowledge.sources,
                error=response.knowledge.error,
                mode=response.mode,
            ).model_dump(),
            "ideas": [idea.model_dump() for idea in response.ideas],
            "assistant_message": "I generated idea options from your experiment log, memory context, and available evidence.",
            "next_action": {
                "type": "select_idea",
                "options": ["select_idea", "continue_search"],
                "message": "Choose one idea to explore further, or continue with contextual search.",
            },
            "suggested_user_actions": [
                "Pick one idea for a small validation experiment.",
                "Use supporting evidence to decide which idea is safest.",
                "Continue with search if you want more papers around a selected idea.",
            ],
        }

    def format_assistant_response(state: dict) -> dict:
        return state

    return {
        "load_memory_context": load_memory_context,
        "assess_query_coverage": assess_query_coverage,
        "route_request": route_request,
        "run_basic_explore": run_basic_explore,
        "run_advanced_ready": run_advanced_ready,
        "run_advanced_search": run_advanced_search,
        "run_research_idea": run_research_idea,
        "format_assistant_response": format_assistant_response,
    }


def route_by_state(state: dict) -> str:
    return state["route"]


def _run_discovery(discovery_graph, state: dict, enabled: bool) -> tuple[ResearchDiscoverySection, list[dict]]:
    if not enabled:
        return ResearchDiscoverySection(enabled=False), []
    try:
        result = discovery_graph.invoke(
            {
                "mode": state["mode"],
                "user_query": state["query"],
                "memory_context": "",
                "rewritten_queries": [],
                "raw_results": [],
                "normalized_papers": [],
                "deduped_papers": [],
                "judge_results": [],
                "ranked_candidates": [],
            }
        )
        return ResearchDiscoverySection(
            enabled=True,
            candidates=result["ranked_candidates"][: state["top_k"]],
            error=None,
        ), []
    except Exception as exc:
        message = str(exc)
        return ResearchDiscoverySection(enabled=True, candidates=[], error=message), [
            {"section": "discovery", "message": message}
        ]


def _run_knowledge(knowledge_qa_service, state: dict, enabled: bool) -> tuple[ResearchKnowledgeSection, list[dict]]:
    if not enabled:
        return ResearchKnowledgeSection(enabled=False), []
    try:
        response = knowledge_qa_service.answer(state["query"], top_k=state["top_k"])
        return _knowledge_section(enabled=True, response=response), []
    except QAServiceError as exc:
        return ResearchKnowledgeSection(enabled=True, answer=None, sources=[], error=exc.detail, mode=None), [
            {"section": "knowledge", "message": exc.detail}
        ]


def _knowledge_from_state_or_service(
    knowledge_qa_service,
    state: dict,
    enabled: bool,
) -> tuple[ResearchKnowledgeSection, list[dict]]:
    cached_knowledge = state.get("knowledge")
    if cached_knowledge and (cached_knowledge.get("answer") is not None or cached_knowledge.get("error") is not None):
        knowledge = ResearchKnowledgeSection(**{**cached_knowledge, "enabled": enabled})
        if knowledge.error is not None and enabled:
            return knowledge, [{"section": "knowledge", "message": knowledge.error}]
        return knowledge, []
    return _run_knowledge(knowledge_qa_service, state, enabled=enabled)


def _knowledge_section(enabled: bool, response) -> ResearchKnowledgeSection:
    return ResearchKnowledgeSection(
        enabled=enabled,
        answer=response.answer,
        sources=response.sources,
        error=None,
        mode=response.mode,
    )


def _semantic_memory_text(memory_context: str) -> str:
    return memory_context.split("Recent episodic memory:", 1)[0]


def _recent_log_text(memory_context: str) -> str:
    if "Recent episodic memory:" not in memory_context:
        return ""
    return memory_context.split("Recent episodic memory:", 1)[1]
