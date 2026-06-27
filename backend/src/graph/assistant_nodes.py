from __future__ import annotations

from graph.errors import DiscoveryStageError
from services.coverage import calculate_coverage_score
from services.idea_service import IdeaServiceError
from services.qa_service import QAServiceError
from services.retrieval_service import RetrievalServiceError
from services.schemas import (
    DiscoveryResult,
    IdeaResult,
    KnowledgeResult,
    ResearchDiscoverySection,
    ResearchKnowledgeSection,
)


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
            errors = errors + [_stage_error("coverage", exc.detail)]
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
        if state.get("experiment_log") is not None:
            return {
                "mode": "advanced",
                "route": "research_idea",
                "route_reason": "current request includes an experiment log",
            }
        if intent == "research":
            return {
                "mode": "advanced",
                "route": "research_idea",
                "route_reason": "research intent requested idea generation",
            }
        if intent == "search":
            return {
                "mode": "advanced",
                "route": "advanced_search",
                "route_reason": "search intent requested contextual discovery and grounded QA",
            }
        if state["coverage_score"] >= ADVANCED_THRESHOLD:
            return {"mode": "advanced", "route": "advanced_ready"}
        return {"mode": "basic", "route": "basic_explore"}

    def run_basic_explore(state: dict) -> dict:
        discovery, errors, discovery_metadata = _run_discovery(discovery_graph, state, enabled=True)
        knowledge, knowledge_errors = _knowledge_from_state_or_service(knowledge_qa_service, state, enabled=True)
        errors.extend(knowledge_errors)
        return {
            "discovery": discovery.model_dump(),
            "knowledge": knowledge.model_dump(),
            "discovery_result": _discovery_result_from_section(
                discovery,
                **discovery_metadata,
            ).model_dump(),
            "knowledge_result": _knowledge_result_from_section(knowledge).model_dump(),
            "idea_result": _empty_idea_result().model_dump(),
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
            "discovery_result": DiscoveryResult(enabled=False).model_dump(),
            "knowledge_result": KnowledgeResult(enabled=False).model_dump(),
            "idea_result": _empty_idea_result().model_dump(),
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
        discovery, errors, discovery_metadata = _run_discovery(discovery_graph, state, enabled=True)
        knowledge, knowledge_errors = _knowledge_from_state_or_service(knowledge_qa_service, state, enabled=True)
        errors.extend(knowledge_errors)
        return {
            "discovery": discovery.model_dump(),
            "knowledge": knowledge.model_dump(),
            "discovery_result": _discovery_result_from_section(
                discovery,
                **discovery_metadata,
            ).model_dump(),
            "knowledge_result": _knowledge_result_from_section(knowledge).model_dump(),
            "idea_result": _empty_idea_result().model_dump(),
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
                "errors": state["errors"]
                + [
                    _stage_error(
                        "idea_generation",
                        "experiment_log is required for research intent",
                        recoverable=False,
                    )
                ]
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
            discovery = ResearchDiscoverySection(enabled=False)
            knowledge = ResearchKnowledgeSection(enabled=False)
            return {
                "discovery": discovery.model_dump(),
                "knowledge": knowledge.model_dump(),
                "ideas": [],
                "discovery_result": _discovery_result_from_section(discovery).model_dump(),
                "knowledge_result": _knowledge_result_from_section(knowledge).model_dump(),
                "idea_result": IdeaResult(enabled=True, error=exc.detail).model_dump(),
                "assistant_message": "I could not generate idea recommendations from this experiment log.",
                "errors": state["errors"]
                + [_stage_error("idea_generation", exc.detail, recoverable=exc.status_code >= 500)],
            }
        discovery = ResearchDiscoverySection(
            enabled=response.discovery.enabled,
            candidates=response.discovery.candidates,
            error=response.discovery.error,
        )
        knowledge = ResearchKnowledgeSection(
            enabled=True,
            answer=None,
            sources=response.knowledge.sources,
            error=response.knowledge.error,
            mode=response.mode,
        )
        return {
            "discovery": discovery.model_dump(),
            "knowledge": knowledge.model_dump(),
            "ideas": [idea.model_dump() for idea in response.ideas],
            "discovery_result": _discovery_result_from_section(discovery).model_dump(),
            "knowledge_result": _knowledge_result_from_section(knowledge).model_dump(),
            "idea_result": IdeaResult(
                enabled=True,
                ideas=response.ideas,
                supporting_evidence=[
                    evidence
                    for idea in response.ideas
                    for evidence in idea.supporting_evidence
                ],
                log_id=response.log_id,
                error=None,
            ).model_dump(),
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


def _run_discovery(
    discovery_graph,
    state: dict,
    enabled: bool,
) -> tuple[ResearchDiscoverySection, list[dict], dict]:
    empty_metadata = {
        "rewritten_queries": [],
        "total_raw": 0,
        "total_deduped": 0,
        "ranked_count": 0,
    }
    if not enabled:
        return ResearchDiscoverySection(enabled=False), [], empty_metadata
    try:
        result = discovery_graph.invoke(
            {
                "mode": state["mode"],
                "user_query": state["query"],
                "memory_context": state["memory_context"],
                "memory_context_is_snapshot": True,
                "rewritten_queries": [],
                "raw_results": [],
                "normalized_papers": [],
                "deduped_papers": [],
                "judge_results": [],
                "ranked_candidates": [],
            }
        )
        ranked_candidates = result["ranked_candidates"]
        return ResearchDiscoverySection(
            enabled=True,
            candidates=ranked_candidates[: state["top_k"]],
            error=None,
        ), [], {
            "rewritten_queries": result.get("rewritten_queries", []),
            "total_raw": len(result.get("raw_results", [])),
            "total_deduped": len(result.get("deduped_papers", [])),
            "ranked_count": len(ranked_candidates),
        }
    except DiscoveryStageError as exc:
        return ResearchDiscoverySection(enabled=True, candidates=[], error=exc.detail), [
            _stage_error(exc.stage, exc.detail, recoverable=exc.recoverable)
        ], empty_metadata


def _run_knowledge(knowledge_qa_service, state: dict, enabled: bool) -> tuple[ResearchKnowledgeSection, list[dict]]:
    if not enabled:
        return ResearchKnowledgeSection(enabled=False), []
    try:
        response = knowledge_qa_service.answer(state["query"], top_k=state["top_k"])
        return _knowledge_section(enabled=True, response=response), []
    except QAServiceError as exc:
        return ResearchKnowledgeSection(enabled=True, answer=None, sources=[], error=exc.detail, mode=None), [
            _stage_error("knowledge_answer", exc.detail)
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
            return knowledge, [_stage_error("knowledge_answer", knowledge.error)]
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


def _stage_error(stage: str, message: str, recoverable: bool = True) -> dict:
    return {"stage": stage, "message": message, "recoverable": recoverable}


def _discovery_result_from_section(
    discovery: ResearchDiscoverySection,
    rewritten_queries: list[str] | None = None,
    total_raw: int = 0,
    total_deduped: int = 0,
    ranked_count: int | None = None,
) -> DiscoveryResult:
    candidates = discovery.candidates
    return DiscoveryResult(
        enabled=discovery.enabled,
        top_k=candidates,
        rewritten_queries=rewritten_queries or [],
        total_raw=total_raw,
        total_deduped=total_deduped,
        scoring_summary={"ranked_count": ranked_count if ranked_count is not None else len(candidates)},
        error=discovery.error,
    )


def _knowledge_result_from_section(knowledge: ResearchKnowledgeSection) -> KnowledgeResult:
    return KnowledgeResult(
        enabled=knowledge.enabled,
        answer=knowledge.answer,
        sources=knowledge.sources,
        mode=knowledge.mode,
        error=knowledge.error,
    )


def _empty_idea_result() -> IdeaResult:
    return IdeaResult(enabled=False)


def _semantic_memory_text(memory_context: str) -> str:
    return memory_context.split("Recent episodic memory:", 1)[0]


def _recent_log_text(memory_context: str) -> str:
    if "Recent episodic memory:" not in memory_context:
        return ""
    return memory_context.split("Recent episodic memory:", 1)[1]
