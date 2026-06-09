from __future__ import annotations

from dataclasses import dataclass

from services.qa_service import KnowledgeQAService, QAServiceError
from services.schemas import (
    ResearchDiscoverySection,
    ResearchKnowledgeSection,
    ResearchQueryResponse,
)


class ResearchWorkflowError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass
class ResearchWorkflowService:
    discovery_graph: object
    knowledge_qa_service: KnowledgeQAService

    def query(
        self,
        query: str,
        mode: str = "basic",
        include_discovery: bool = True,
        include_knowledge: bool = True,
        top_k: int = 5,
    ) -> ResearchQueryResponse:
        normalized_query = query.strip()
        if not normalized_query:
            raise ResearchWorkflowError("query must not be empty", status_code=400)
        if not include_discovery and not include_knowledge:
            raise ResearchWorkflowError("at least one of discovery or knowledge must be enabled", status_code=400)

        discovery = ResearchDiscoverySection(enabled=include_discovery, candidates=[], error=None)
        knowledge = ResearchKnowledgeSection(enabled=include_knowledge, answer=None, sources=[], error=None, mode=None)

        discovery_error: tuple[str, int] | None = None
        knowledge_error: tuple[str, int] | None = None

        if include_discovery:
            try:
                result = self.discovery_graph.invoke(
                    {
                        "mode": mode,
                        "user_query": normalized_query,
                        "memory_context": "",
                        "rewritten_queries": [],
                        "raw_results": [],
                        "normalized_papers": [],
                        "deduped_papers": [],
                        "judge_results": [],
                        "ranked_candidates": [],
                    }
                )
                discovery.candidates = result["ranked_candidates"][:top_k]
            except Exception as exc:
                discovery_error = (str(exc), 502)
                discovery.error = str(exc)

        if include_knowledge:
            try:
                answer = self.knowledge_qa_service.answer(normalized_query, top_k=top_k)
                knowledge.answer = answer.answer
                knowledge.sources = answer.sources
                knowledge.mode = answer.mode
            except QAServiceError as exc:
                knowledge_error = (exc.detail, exc.status_code)
                knowledge.error = exc.detail

        if include_discovery and not include_knowledge and discovery_error is not None:
            raise ResearchWorkflowError(discovery_error[0], status_code=discovery_error[1])
        if include_knowledge and not include_discovery and knowledge_error is not None:
            raise ResearchWorkflowError(knowledge_error[0], status_code=knowledge_error[1])

        return ResearchQueryResponse(
            query=normalized_query,
            mode=mode,
            discovery=discovery,
            knowledge=knowledge,
        )
