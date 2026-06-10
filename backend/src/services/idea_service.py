from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.retrieval_service import KnowledgeRetrievalService, RetrievalServiceError
from services.schemas import (
    IdeaDiscoverySection,
    ExperimentLogRequest,
    IdeaKnowledgeSection,
    IdeaRecommendResponse,
    IdeaOption,
    IdeaSupportingEvidence,
    KnowledgeSearchResult,
    KnowledgeAnswerSource,
)


class IdeaServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class IdeaGenerator(Protocol):
    def generate(
        self,
        experiment_log: ExperimentLogRequest,
        retrieved_chunks: list[KnowledgeSearchResult],
        discovery_candidates: list[dict],
        idea_count: int,
    ) -> list[IdeaOption]:
        """Generate structured idea options from a structured experiment log and evidence."""


@dataclass
class DeterministicIdeaGenerator:
    def generate(
        self,
        experiment_log: ExperimentLogRequest,
        retrieved_chunks: list[KnowledgeSearchResult],
        discovery_candidates: list[dict],
        idea_count: int,
    ) -> list[IdeaOption]:
        evidence = self._knowledge_evidence(retrieved_chunks)
        rationale_prefix = (
            "Use the retrieved local knowledge evidence and the experiment log"
            if evidence
            else "No local knowledge evidence was found; use this as a conservative hypothesis from the experiment log"
        )
        templates = [
            IdeaOption(
                title="Tune a precision-aware decision threshold",
                rationale=f"{rationale_prefix} to separate representation learning from operating-point selection.",
                supporting_evidence=evidence[:1],
                expected_benefit=f"May improve {experiment_log.metric_problem} without changing the {experiment_log.model} architecture.",
                risk="Threshold tuning can overfit if the validation split is small or distribution-shifted.",
                suggested_validation_metric="minority-class PRAUC with a precision floor",
                next_small_experiment="Keep the trained checkpoint fixed and sweep decision thresholds on the validation split.",
            ),
            IdeaOption(
                title="Add a lightweight calibration step after imbalance training",
                rationale=f"{rationale_prefix} to test whether score calibration can reduce precision collapse.",
                supporting_evidence=evidence[:1],
                expected_benefit="May improve ranking quality and precision-recall tradeoffs with little inference overhead.",
                risk="Calibration may hide dataset leakage or become unstable on very small minority-class validation sets.",
                suggested_validation_metric="minority-class PRAUC plus expected calibration error",
                next_small_experiment="Fit a simple calibration layer on validation logits and compare PRAUC against the current focal-loss run.",
            ),
            IdeaOption(
                title="Use hard-negative focused sampling for the minority class",
                rationale=f"{rationale_prefix} to target false positives instead of only increasing recall.",
                supporting_evidence=evidence[:1],
                expected_benefit="May recover precision while preserving the recall gain from imbalance-aware training.",
                risk="Oversampling hard negatives can reduce generalization if the negatives are noisy or mislabeled.",
                suggested_validation_metric="minority-class PRAUC and precision at fixed recall",
                next_small_experiment="Run one training job that oversamples hard negatives from recent false-positive errors.",
            ),
            IdeaOption(
                title="Compare focal loss against class-balanced loss at fixed model size",
                rationale=f"{rationale_prefix} to isolate the loss-function effect from model capacity.",
                supporting_evidence=evidence[:1],
                expected_benefit="May improve minority ranking while keeping the model lightweight.",
                risk="Loss changes can improve one minority class while degrading macro behavior.",
                suggested_validation_metric="minority-class PRAUC, macro PRAUC, and parameter count",
                next_small_experiment="Train the same 1D-CNN with class-balanced loss and compare against focal loss using identical seeds.",
            ),
            IdeaOption(
                title="Audit minority-class label noise before adding capacity",
                rationale=f"{rationale_prefix} to check whether precision collapse comes from noisy labels or ambiguous windows.",
                supporting_evidence=evidence[:1],
                expected_benefit="May reveal a data issue that can be fixed without making the model heavier.",
                risk="Manual or heuristic auditing may be slow and can bias the validation process.",
                suggested_validation_metric="minority-class PRAUC before and after removing suspicious validation windows",
                next_small_experiment="Inspect the top false positives and false negatives, then rerun metrics after flagging ambiguous samples.",
            ),
        ]
        return templates[:idea_count]

    def _knowledge_evidence(self, chunks: list[KnowledgeSearchResult]) -> list[IdeaSupportingEvidence]:
        return [
            IdeaSupportingEvidence(
                source_type="knowledge",
                paper_id=chunk.paper_id,
                title=chunk.title,
                chunk_index=chunk.chunk_index,
                distance=chunk.distance,
                text=chunk.text,
                vector_ref=chunk.vector_ref,
            )
            for chunk in chunks
        ]


@dataclass
class IdeaRecommendationService:
    store: object
    retrieval_service: KnowledgeRetrievalService
    idea_generator: IdeaGenerator
    discovery_graph: object | None = None
    mode: str = "deterministic"

    def recommend(
        self,
        experiment_log: ExperimentLogRequest,
        save_log: bool = True,
        include_discovery: bool = False,
        top_k: int = 5,
        idea_count: int = 3,
    ) -> IdeaRecommendResponse:
        query = self.build_query(experiment_log)
        if not query:
            raise IdeaServiceError("experiment log produced an empty query", status_code=400)

        log_id = None
        if save_log:
            log_id = self.store.add_experiment_log_entry(experiment_log.model_dump())

        knowledge_sources: list[KnowledgeAnswerSource] = []
        knowledge_error = None
        retrieved_chunks: list[KnowledgeSearchResult] = []

        try:
            retrieval_response = self.retrieval_service.search(query, top_k=top_k)
            retrieved_chunks = retrieval_response.results
            knowledge_sources = [
                KnowledgeAnswerSource(
                    paper_id=result.paper_id,
                    title=result.title,
                    chunk_index=result.chunk_index,
                    distance=result.distance,
                    text=result.text,
                    vector_ref=result.vector_ref,
                )
                for result in retrieved_chunks
            ]
        except RetrievalServiceError as exc:
            knowledge_error = exc.detail
            raise IdeaServiceError(exc.detail, status_code=exc.status_code) from exc

        discovery = IdeaDiscoverySection(enabled=include_discovery, candidates=[], error=None)
        if include_discovery and self.discovery_graph is not None:
            try:
                discovery_result = self.discovery_graph.invoke(
                    {
                        "mode": "basic",
                        "user_query": query,
                        "memory_context": "",
                        "rewritten_queries": [],
                        "raw_results": [],
                        "normalized_papers": [],
                        "deduped_papers": [],
                        "judge_results": [],
                        "ranked_candidates": [],
                    }
                )
                discovery.candidates = discovery_result["ranked_candidates"][:top_k]
            except Exception as exc:
                discovery.error = str(exc)

        ideas = self.idea_generator.generate(
            experiment_log=experiment_log,
            retrieved_chunks=retrieved_chunks,
            discovery_candidates=discovery.candidates,
            idea_count=idea_count,
        )

        return IdeaRecommendResponse(
            log_id=log_id,
            query=query,
            knowledge=IdeaKnowledgeSection(sources=knowledge_sources, error=knowledge_error),
            discovery=discovery,
            ideas=ideas,
            mode=self.mode,
        )

    def build_query(self, experiment_log: ExperimentLogRequest) -> str:
        parts = [
            experiment_log.task,
            experiment_log.model,
            experiment_log.dataset,
            experiment_log.metric_problem,
            experiment_log.observation,
            experiment_log.goal,
            " ".join(experiment_log.tried_methods),
        ]
        memory_context = self.store.build_memory_context()
        if memory_context.strip():
            parts.append(memory_context)
        return " ".join(part.strip() for part in parts if part and part.strip())
