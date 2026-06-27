from __future__ import annotations

from dataclasses import dataclass

from graph.builder import build_research_assistant_graph
from services.schemas import (
    DiscoveryResult,
    ExperimentLogRequest,
    IdeaResult,
    KnowledgeResult,
    ResearchAssistantError,
    ResearchAssistantNextAction,
    ResearchAssistantResponse,
    ResearchDiscoverySection,
    ResearchKnowledgeSection,
)


class ResearchAssistantWorkflowError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass
class ResearchAssistantWorkflowService:
    store: object
    discovery_graph: object
    knowledge_qa_service: object
    idea_service: object

    def query(
        self,
        query: str,
        intent: str = "auto",
        experiment_log: ExperimentLogRequest | None = None,
        top_k: int = 5,
        idea_count: int = 3,
        save_log: bool = True,
        include_discovery: bool = False,
    ) -> ResearchAssistantResponse:
        normalized_query = query.strip()
        if not normalized_query:
            raise ResearchAssistantWorkflowError("query must not be empty", status_code=400)
        if intent == "research" and experiment_log is None:
            raise ResearchAssistantWorkflowError("experiment_log is required for research intent", status_code=400)

        graph = build_research_assistant_graph(
            store=self.store,
            discovery_graph=self.discovery_graph,
            knowledge_qa_service=self.knowledge_qa_service,
            idea_service=self.idea_service,
        )
        result = graph.invoke(
            {
                "query": normalized_query,
                "intent": intent,
                "experiment_log": experiment_log,
                "top_k": top_k,
                "idea_count": idea_count,
                "save_log": save_log,
                "include_discovery": include_discovery,
                "memory_context": "",
                "coverage_score": 0.0,
                "mode": "basic",
                "route": "basic_explore",
                "route_reason": "",
                "discovery": ResearchDiscoverySection(enabled=False).model_dump(),
                "knowledge": ResearchKnowledgeSection(enabled=False).model_dump(),
                "ideas": [],
                "discovery_result": DiscoveryResult(enabled=False).model_dump(),
                "knowledge_result": KnowledgeResult(enabled=False).model_dump(),
                "idea_result": IdeaResult(enabled=False).model_dump(),
                "assistant_message": "",
                "next_action": None,
                "suggested_user_actions": [],
                "errors": [],
            }
        )

        return ResearchAssistantResponse(
            query=result["query"],
            intent=result["intent"],
            mode=result["mode"],
            route=result["route"],
            coverage_score=result["coverage_score"],
            route_reason=result["route_reason"],
            assistant_message=result["assistant_message"],
            next_action=(
                ResearchAssistantNextAction(**result["next_action"])
                if result.get("next_action") is not None
                else None
            ),
            suggested_user_actions=result["suggested_user_actions"],
            discovery=ResearchDiscoverySection(**result["discovery"]),
            knowledge=ResearchKnowledgeSection(**result["knowledge"]),
            ideas=result["ideas"],
            discovery_result=DiscoveryResult(**result["discovery_result"]),
            knowledge_result=KnowledgeResult(**result["knowledge_result"]),
            idea_result=IdeaResult(**result["idea_result"]),
            errors=[ResearchAssistantError(**error) for error in result["errors"]],
        )
