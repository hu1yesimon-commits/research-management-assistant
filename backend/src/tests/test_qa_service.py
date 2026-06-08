from services.answer_service import FakeGroundedAnswerGenerator
from services.embedding_service import FakeEmbeddingService
from services.memory_store import MemoryStore
from services.qa_service import KnowledgeQAService, QAServiceError
from services.retrieval_service import KnowledgeRetrievalService
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


def build_service(store: MemoryStore, vector_store: FakeVectorStoreService) -> KnowledgeQAService:
    retrieval_service = KnowledgeRetrievalService(
        store=store,
        embedding_service=FakeEmbeddingService(),
        vector_store_service=vector_store,
    )
    return KnowledgeQAService(
        retrieval_service=retrieval_service,
        answer_generator=FakeGroundedAnswerGenerator(),
    )


class TrackingAnswerGenerator:
    def __init__(self, answer: str = "tracked answer"):
        self.answer = answer
        self.calls: list[tuple[str, list]] = []

    def generate(self, question: str, retrieved_chunks: list) -> str:
        self.calls.append((question, retrieved_chunks))
        return self.answer


def test_qa_service_returns_answer_and_sources_from_retrieval_results(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    vector_store = FakeVectorStoreService()
    seed_embedded_chunk(store, vector_store, "paper-1", "Paper One", "graph reconstruction uses priors")

    response = build_service(store, vector_store).answer("How do I do graph reconstruction?", top_k=5)

    assert response.question == "How do I do graph reconstruction?"
    assert response.mode == "deterministic"
    assert response.sources[0].paper_id == "paper-1"
    assert "Paper One" in response.answer


def test_qa_service_returns_fallback_answer_when_no_results_exist(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    response = build_service(store, FakeVectorStoreService()).answer("missing topic", top_k=5)

    assert response.answer == "No relevant knowledge chunks were found."
    assert response.sources == []


def test_qa_service_does_not_call_answer_generator_when_no_results_exist(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    retrieval_service = KnowledgeRetrievalService(
        store=store,
        embedding_service=FakeEmbeddingService(),
        vector_store_service=FakeVectorStoreService(),
    )
    generator = TrackingAnswerGenerator()

    response = KnowledgeQAService(
        retrieval_service=retrieval_service,
        answer_generator=generator,
        mode="llm",
    ).answer("missing topic", top_k=5)

    assert response.answer == "No relevant knowledge chunks were found."
    assert response.mode == "llm"
    assert generator.calls == []


def test_qa_service_rejects_blank_question(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    try:
        build_service(store, FakeVectorStoreService()).answer("   ", top_k=5)
    except QAServiceError as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("expected QAServiceError")
