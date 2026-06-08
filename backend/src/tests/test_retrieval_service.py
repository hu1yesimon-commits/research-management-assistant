from services.embedding_service import FakeEmbeddingService
from services.memory_store import MemoryStore
from services.retrieval_service import KnowledgeRetrievalService, RetrievalServiceError
from services.schemas import JudgeResult, PaperId, PaperMetadata
from services.vector_store import FakeVectorStoreService, build_chunk_uid


def make_paper(paper_id: str, title: str) -> PaperMetadata:
    return PaperMetadata(
        paper_id=paper_id,
        source_ids=PaperId(doi=f"10.1000/{paper_id}"),
        title=title,
        authors=["Tester"],
        abstract=f"Abstract for {paper_id}",
        doi=f"10.1000/{paper_id}",
        source="test",
    )


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


def seed_embedded_chunk(store: MemoryStore, vector_store: FakeVectorStoreService, paper_id: str, title: str, text: str) -> None:
    paper = make_paper(paper_id, title)
    store.save_candidate_paper(paper, make_judgement())
    store.update_paper_status(paper_id, "embedded", pdf_path=f"/tmp/{paper_id}.pdf")
    chunk_hash = f"hash-{paper_id}"
    chunk_uid = build_chunk_uid(paper_id, 0, chunk_hash)
    vector_ref = vector_store.upsert_chunks(
        [{"chunk_uid": chunk_uid, "paper_id": paper_id, "chunk_index": 0, "text": text}],
        embeddings=[FakeEmbeddingService().embed_texts([text])[0]],
    )[0]
    store.insert_knowledge_chunks(
        paper_id,
        [{"chunk_index": 0, "text": text, "chunk_hash": chunk_hash, "vector_ref": vector_ref}],
    )


def test_knowledge_retrieval_service_returns_enriched_results_for_embedded_chunks(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    vector_store = FakeVectorStoreService()
    seed_embedded_chunk(store, vector_store, "paper-1", "Paper One", "graph reconstruction survey")
    seed_embedded_chunk(store, vector_store, "paper-2", "Paper Two", "protein folding methods")

    service = KnowledgeRetrievalService(
        store=store,
        embedding_service=FakeEmbeddingService(),
        vector_store_service=vector_store,
    )

    response = service.search("graph reconstruction", top_k=2)

    assert response.query == "graph reconstruction"
    assert len(response.results) == 2
    assert response.results[0].paper_id == "paper-1"
    assert response.results[0].title == "Paper One"
    assert response.results[0].vector_ref.startswith("chroma:research_chunks:")


def test_knowledge_retrieval_service_returns_empty_results_when_no_embedded_chunks_exist(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    service = KnowledgeRetrievalService(
        store=store,
        embedding_service=FakeEmbeddingService(),
        vector_store_service=FakeVectorStoreService(),
    )

    response = service.search("graph reconstruction", top_k=5)

    assert response.results == []


def test_knowledge_retrieval_service_rejects_blank_query(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    service = KnowledgeRetrievalService(
        store=store,
        embedding_service=FakeEmbeddingService(),
        vector_store_service=FakeVectorStoreService(),
    )

    try:
        service.search("   ", top_k=5)
    except RetrievalServiceError as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("expected RetrievalServiceError")
