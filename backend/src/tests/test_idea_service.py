from services.embedding_service import FakeEmbeddingService
from services.idea_service import DeterministicIdeaGenerator, IdeaRecommendationService
from services.memory_store import MemoryStore
from services.retrieval_service import KnowledgeRetrievalService
from services.schemas import (
    ExperimentLogRequest,
    JudgeResult,
    PaperId,
    PaperMetadata,
    KnowledgeSearchResult,
)
from services.vector_store import FakeVectorStoreService, build_chunk_uid


def make_log() -> ExperimentLogRequest:
    return ExperimentLogRequest(
        task="defect classification",
        model="1D-CNN",
        dataset="bearing fault dataset",
        metric_problem="minority class PRAUC is low",
        tried_methods=["class weighting", "focal loss"],
        observation="recall improves but precision collapses",
        goal="improve PRAUC without making model too heavy",
        tags=["imbalanced-learning"],
    )


def test_deterministic_idea_generator_returns_requested_count_with_knowledge_evidence():
    chunk = KnowledgeSearchResult(
        paper_id="paper-1",
        title="Imbalanced Fault Diagnosis",
        chunk_index=0,
        text="Precision-recall metrics are useful for imbalanced classification.",
        vector_ref="chroma:research_chunks:paper-1:0:hash",
        distance=0.1,
    )

    ideas = DeterministicIdeaGenerator().generate(
        experiment_log=make_log(),
        retrieved_chunks=[chunk],
        discovery_candidates=[],
        idea_count=3,
    )

    assert len(ideas) == 3
    assert all(idea.supporting_evidence for idea in ideas)
    assert ideas[0].supporting_evidence[0].source_type == "knowledge"
    assert ideas[0].supporting_evidence[0].paper_id == "paper-1"
    assert "PRAUC" in ideas[0].suggested_validation_metric


def test_deterministic_idea_generator_does_not_invent_evidence_without_sources():
    ideas = DeterministicIdeaGenerator().generate(
        experiment_log=make_log(),
        retrieved_chunks=[],
        discovery_candidates=[],
        idea_count=3,
    )

    assert len(ideas) == 3
    assert all(idea.supporting_evidence == [] for idea in ideas)
    assert "No local knowledge evidence" in ideas[0].rationale


def make_judgement() -> JudgeResult:
    return JudgeResult(
        decision="accept",
        reason="Relevant",
        llm_relevance_score=0.9,
        embedding_relevance_score=0.8,
        quality_score=0.7,
        novelty_score=1.0,
        final_score=0.85,
        tags=["fake"],
    )


def seed_embedded_chunk(store: MemoryStore, vector_store: FakeVectorStoreService) -> None:
    paper = PaperMetadata(
        paper_id="paper-1",
        source_ids=PaperId(doi="10.1000/paper-1"),
        title="Imbalanced Fault Diagnosis",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/paper-1",
        source="test",
    )
    store.save_candidate_paper(paper, make_judgement())
    store.update_paper_status(paper.paper_id, "embedded", pdf_path="/tmp/paper-1.pdf")
    chunk_text = "Precision-recall metrics are useful for imbalanced classification."
    chunk_hash = "hash-0"
    chunk_uid = build_chunk_uid(paper.paper_id, 0, chunk_hash)
    vector_ref = vector_store.upsert_chunks(
        [{"chunk_uid": chunk_uid, "paper_id": paper.paper_id, "chunk_index": 0, "text": chunk_text}],
        embeddings=[FakeEmbeddingService().embed_texts([chunk_text])[0]],
    )[0]
    store.insert_knowledge_chunks(
        paper.paper_id,
        [{"chunk_index": 0, "text": chunk_text, "chunk_hash": chunk_hash, "vector_ref": vector_ref}],
    )


def build_recommendation_service(store: MemoryStore, vector_store: FakeVectorStoreService) -> IdeaRecommendationService:
    retrieval_service = KnowledgeRetrievalService(
        store=store,
        embedding_service=FakeEmbeddingService(),
        vector_store_service=vector_store,
    )
    return IdeaRecommendationService(
        store=store,
        retrieval_service=retrieval_service,
        idea_generator=DeterministicIdeaGenerator(),
        discovery_graph=None,
        mode="deterministic",
    )


def test_idea_recommendation_service_saves_log_retrieves_sources_and_returns_ideas(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    vector_store = FakeVectorStoreService()
    seed_embedded_chunk(store, vector_store)

    response = build_recommendation_service(store, vector_store).recommend(
        experiment_log=make_log(),
        save_log=True,
        include_discovery=False,
        top_k=5,
        idea_count=3,
    )

    assert response.log_id == 1
    assert "defect classification" in response.query
    assert response.knowledge.sources[0].paper_id == "paper-1"
    assert response.discovery.enabled is False
    assert len(response.ideas) == 3
    assert response.mode == "deterministic"


def test_idea_recommendation_service_can_return_no_source_fallback_without_saving_log(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    response = build_recommendation_service(store, FakeVectorStoreService()).recommend(
        experiment_log=make_log(),
        save_log=False,
        include_discovery=False,
        top_k=5,
        idea_count=3,
    )

    assert response.log_id is None
    assert response.knowledge.sources == []
    assert len(response.ideas) == 3
    assert store.list_experiment_log_entries() == []


def test_idea_service_query_includes_confirmed_semantic_memory(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    store.add_experiment_log("legacy lightweight note should not be required", tags=["legacy"])
    candidate_id = store.upsert_memory_candidate(
        {
            "candidate_type": "semantic_proposal",
            "category": "user_preference",
            "subject": "user",
            "predicate": "prefers",
            "object": "lightweight",
            "summary": "User repeatedly prefers lightweight approaches.",
            "source_log_ids": [1, 2, 3],
            "evidence_count": 3,
            "score": 0.8,
            "status": "pending",
        }
    )
    store.upsert_semantic_memory_from_candidate(store.get_memory_candidate(candidate_id))
    service = build_recommendation_service(store, FakeVectorStoreService())

    query = service.build_query(
        ExperimentLogRequest(
            task="defect classification",
            model="1D-CNN",
            dataset="bearing fault dataset",
            metric_problem="minority PRAUC is low",
            tried_methods=["focal loss"],
            observation="recall improves but precision collapses",
            goal="improve PRAUC",
            tags=[],
        )
    )

    assert "lightweight" in query
    assert "legacy lightweight note should not be required" not in query


def test_idea_recommendation_service_continues_when_discovery_fails(tmp_path):
    class FailingDiscoveryGraph:
        def invoke(self, payload):
            raise RuntimeError("discovery offline")

    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    service = IdeaRecommendationService(
        store=store,
        retrieval_service=KnowledgeRetrievalService(
            store=store,
            embedding_service=FakeEmbeddingService(),
            vector_store_service=FakeVectorStoreService(),
        ),
        idea_generator=DeterministicIdeaGenerator(),
        discovery_graph=FailingDiscoveryGraph(),
        mode="deterministic",
    )

    response = service.recommend(
        experiment_log=make_log(),
        save_log=False,
        include_discovery=True,
        top_k=5,
        idea_count=3,
    )

    assert response.discovery.enabled is True
    assert response.discovery.error == "discovery offline"
    assert response.discovery.candidates == []
    assert len(response.ideas) == 3
