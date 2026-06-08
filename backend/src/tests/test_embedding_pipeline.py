from services.embedding_pipeline import EmbeddingPipelineError, EmbeddingPipelineService
from services.embedding_service import FakeEmbeddingService
from services.knowledge_base import KnowledgeBase
from services.memory_store import MemoryStore
from services.schemas import JudgeResult, PaperId, PaperMetadata
from services.vector_store import FakeVectorStoreService


class FakeKnowledgeBase:
    def __init__(self, extracted_text: str = "Phase 2C extracted text for chunking.", should_fail: bool = False):
        self.extracted_text = extracted_text
        self.should_fail = should_fail

    def extract_text(self, pdf_path: str) -> str:
        if self.should_fail:
            raise ValueError(f"failed to extract text from pdf: {pdf_path}")
        return self.extracted_text

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> list[dict]:
        if self.should_fail:
            raise ValueError("chunking should not run after extraction failure")
        return [
            {"chunk_index": 0, "text": text[:12], "chunk_hash": "hash-0", "vector_ref": None},
            {"chunk_index": 1, "text": text[12:], "chunk_hash": "hash-1", "vector_ref": None},
        ]


class FailingEmbeddingService(FakeEmbeddingService):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise ValueError("fake embedding failure")


def make_paper(paper_id: str) -> PaperMetadata:
    return PaperMetadata(
        paper_id=paper_id,
        source_ids=PaperId(doi=f"10.1000/{paper_id}"),
        title=f"Paper {paper_id}",
        authors=["Tester"],
        abstract="Useful abstract.",
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


def build_pipeline(
    store: MemoryStore,
    knowledge_base=None,
    embedding_service=None,
    vector_store_service=None,
) -> EmbeddingPipelineService:
    return EmbeddingPipelineService(
        store=store,
        knowledge_base=knowledge_base or FakeKnowledgeBase(),
        embedding_service=embedding_service or FakeEmbeddingService(),
        vector_store_service=vector_store_service or FakeVectorStoreService(),
    )


def test_pipeline_runs_phase_2c_for_uploaded_paper(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    paper = make_paper("uploaded-paper")
    store.save_candidate_paper(paper, make_judgement())
    pdf_path = KnowledgeBase(upload_dir=str(tmp_path / "uploads")).save_pdf(
        paper_id=paper.paper_id,
        filename="paper.pdf",
        content=b"%PDF-1.4 fake pdf",
    )
    store.update_paper_status(paper.paper_id, "uploaded", pdf_path=pdf_path)

    result = build_pipeline(store).run(paper.paper_id)

    assert result == {
        "paper_id": paper.paper_id,
        "status": "chunked",
        "pdf_path": pdf_path,
        "chunk_count": 2,
    }
    assert store.get_paper(paper.paper_id)["status"] == "chunked"


def test_pipeline_runs_phase_2d_for_chunked_paper(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    paper = make_paper("chunked-paper")
    store.save_candidate_paper(paper, make_judgement())
    store.update_paper_status(paper.paper_id, "chunked", pdf_path="/tmp/chunked-paper.pdf")
    store.insert_knowledge_chunks(
        paper.paper_id,
        [
            {"chunk_index": 0, "text": "chunk a", "chunk_hash": "hash-a", "vector_ref": None},
            {"chunk_index": 1, "text": "chunk b", "chunk_hash": "hash-b", "vector_ref": None},
        ],
    )

    result = build_pipeline(store).run(paper.paper_id)

    assert result == {
        "paper_id": paper.paper_id,
        "status": "embedded",
        "vector_ref_count": 2,
    }
    assert store.get_paper(paper.paper_id)["status"] == "embedded"


def test_pipeline_keeps_chunked_status_when_phase_2d_fails(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    paper = make_paper("chunked-paper-fail")
    store.save_candidate_paper(paper, make_judgement())
    store.update_paper_status(paper.paper_id, "chunked", pdf_path="/tmp/chunked-paper.pdf")
    store.insert_knowledge_chunks(
        paper.paper_id,
        [{"chunk_index": 0, "text": "chunk a", "chunk_hash": "hash-a", "vector_ref": None}],
    )

    try:
        build_pipeline(store, embedding_service=FailingEmbeddingService()).run(paper.paper_id)
    except EmbeddingPipelineError as exc:
        assert exc.detail == "fake embedding failure"
    else:
        raise AssertionError("expected EmbeddingPipelineError")

    assert store.get_paper(paper.paper_id)["status"] == "chunked"
    assert store.list_knowledge_chunks(paper.paper_id)[0]["vector_ref"] is None
