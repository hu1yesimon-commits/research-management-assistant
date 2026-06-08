from __future__ import annotations

from dataclasses import dataclass

from services.answer_service import AnswerGenerator
from services.retrieval_service import KnowledgeRetrievalService, RetrievalServiceError
from services.schemas import KnowledgeAnswerResponse, KnowledgeAnswerSource


class QAServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass
class KnowledgeQAService:
    retrieval_service: KnowledgeRetrievalService
    answer_generator: AnswerGenerator
    mode: str = "deterministic"

    def answer(self, question: str, top_k: int = 5) -> KnowledgeAnswerResponse:
        normalized_question = question.strip()
        if not normalized_question:
            raise QAServiceError("question must not be empty", status_code=400)

        try:
            retrieval_response = self.retrieval_service.search(normalized_question, top_k=top_k)
        except RetrievalServiceError as exc:
            raise QAServiceError(exc.detail, status_code=exc.status_code) from exc

        sources = [
            KnowledgeAnswerSource(
                paper_id=result.paper_id,
                title=result.title,
                chunk_index=result.chunk_index,
                distance=result.distance,
                text=result.text,
                vector_ref=result.vector_ref,
            )
            for result in retrieval_response.results
        ]

        if not sources:
            return KnowledgeAnswerResponse(
                question=normalized_question,
                answer="No relevant knowledge chunks were found.",
                sources=[],
                mode=self.mode,
            )

        answer = self.answer_generator.generate(normalized_question, retrieval_response.results)
        return KnowledgeAnswerResponse(
            question=normalized_question,
            answer=answer,
            sources=sources,
            mode=self.mode,
        )
