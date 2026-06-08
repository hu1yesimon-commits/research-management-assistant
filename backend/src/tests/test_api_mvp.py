from pathlib import Path

from fastapi.testclient import TestClient

from graph.builder import build_paper_discovery_graph
from main import app, get_knowledge_base, get_memory_store, get_paper_discovery_graph
from services.knowledge_base import KnowledgeBase
from services.query_rewriter import QueryRewriter
from services.schemas import JudgeResult, PaperId, PaperMetadata


class FakeGraph:
    def __init__(self, store):
        self.store = store

    def invoke(self, state: dict) -> dict:
        paper = PaperMetadata(
            paper_id="api-paper-1",
            source_ids=PaperId(doi="10.1000/api-paper-1"),
            title=f"Paper for {state['user_query']}",
            authors=["Tester"],
            abstract="Useful abstract.",
            doi="10.1000/api-paper-1",
            source="test",
        )
        judgement = JudgeResult(
            decision="accept",
            reason="Relevant",
            llm_relevance_score=0.9,
            embedding_relevance_score=0.8,
            quality_score=0.7,
            novelty_score=1.0,
            final_score=0.85,
            tags=["fake"],
        )
        self.store.save_candidate_paper(paper, judgement)
        return {
            **state,
            "rewritten_queries": [state["user_query"]],
            "ranked_candidates": [{"paper": paper, "judgement": judgement}],
        }


class FakeSearchService:
    def search(self, query: str) -> list[PaperMetadata]:
        slug = query.lower().replace(" ", "-")
        return [
            PaperMetadata(
                paper_id=f"api-{slug}",
                source_ids=PaperId(doi=f"10.1000/{slug}"),
                title=f"Paper for {query}",
                authors=["Tester"],
                abstract="Useful abstract.",
                doi=f"10.1000/{slug}",
                source="test",
            )
        ]


class FakeJudge:
    def judge(self, paper: PaperMetadata) -> JudgeResult:
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

    def sort_by_final_score(self, results: list[JudgeResult]) -> list[JudgeResult]:
        return sorted(results, key=lambda item: item.final_score, reverse=True)


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
            {
                "chunk_index": 0,
                "text": text[:12],
                "chunk_hash": "hash-0",
                "vector_ref": None,
            },
            {
                "chunk_index": 1,
                "text": text[12:],
                "chunk_hash": "hash-1",
                "vector_ref": None,
            },
        ]


def override_store_with_path(test_db):
    return lambda: get_memory_store(str(test_db))


def test_health_endpoint_returns_ok():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_logs_endpoint_saves_and_lists_logs(tmp_path):
    test_db = tmp_path / "api.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    client = TestClient(app)

    response = client.post("/logs", json={"content": "loss exploded", "tags": ["block"]})
    assert response.status_code == 200

    logs = client.get("/logs")
    assert logs.status_code == 200
    assert logs.json()[0]["content"] == "loss exploded"

    app.dependency_overrides.clear()


def test_candidates_endpoint_returns_empty_list(tmp_path):
    test_db = tmp_path / "api.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    client = TestClient(app)

    response = client.get("/papers/candidates")

    assert response.status_code == 200
    assert response.json() == []

    app.dependency_overrides.clear()


def test_search_persists_candidates_without_network(tmp_path):
    test_db = tmp_path / "api.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    app.dependency_overrides[get_paper_discovery_graph] = lambda: FakeGraph(get_memory_store(str(test_db)))
    client = TestClient(app)

    response = client.post("/search", json={"mode": "basic", "query": "graph reconstruction"})

    assert response.status_code == 200
    body = response.json()
    assert body[0]["paper"]["paper_id"] == "api-paper-1"

    candidates = client.get("/papers/candidates")
    assert candidates.status_code == 200
    assert candidates.json()[0]["paper_id"] == "api-paper-1"

    summary = client.get("/memory/summary")
    assert summary.status_code == 200
    assert summary.json()["candidate_count"] == 1

    app.dependency_overrides.clear()


def test_advanced_search_uses_deterministic_memory_context_rewriting(tmp_path):
    test_db = tmp_path / "api-advanced.sqlite3"
    store = get_memory_store(str(test_db))
    store.add_experiment_log("model is too heavy", tags=["block"])
    store.add_experiment_log("improve interpretability", tags=["idea"])

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_paper_discovery_graph] = lambda: build_paper_discovery_graph(
        search_service=FakeSearchService(),
        judge=FakeJudge(),
        memory_store=store,
        query_rewriter=QueryRewriter(),
    )
    client = TestClient(app)

    response = client.post("/search", json={"mode": "advanced", "query": "graph reconstruction"})

    assert response.status_code == 200
    body = response.json()
    titles = {item["paper"]["title"] for item in body}
    assert "Paper for graph reconstruction lightweight" in titles
    assert "Paper for graph reconstruction interpretability" in titles

    summary = client.get("/memory/summary")
    assert summary.status_code == 200
    assert summary.json()["candidate_count"] >= 3

    app.dependency_overrides.clear()


def test_upload_pdf_updates_candidate_to_uploaded_and_known_doi(tmp_path):
    test_db = tmp_path / "api-upload.sqlite3"
    upload_dir = tmp_path / "uploads"
    store = get_memory_store(str(test_db))
    paper = PaperMetadata(
        paper_id="upload-paper-1",
        source_ids=PaperId(doi="10.1000/upload-paper-1"),
        title="Upload Paper",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/upload-paper-1",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(paper))

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_knowledge_base] = lambda: KnowledgeBase(upload_dir=str(upload_dir))
    client = TestClient(app)

    response = client.post(
        "/papers/upload-paper-1/upload_pdf",
        files={"file": ("paper.pdf", b"%PDF-1.4 fake pdf", "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["paper_id"] == "upload-paper-1"
    assert body["status"] == "uploaded"
    assert Path(body["pdf_path"]).exists()

    candidates = client.get("/papers/candidates").json()
    assert candidates[0]["status"] == "uploaded"
    assert candidates[0]["pdf_path"] == body["pdf_path"]
    assert client.get("/memory/summary").json()["known_dois"] == ["10.1000/upload-paper-1"]

    app.dependency_overrides.clear()


def test_accept_paper_updates_candidate_to_accepted(tmp_path):
    test_db = tmp_path / "api-accept.sqlite3"
    store = get_memory_store(str(test_db))
    paper = PaperMetadata(
        paper_id="accept-paper-1",
        source_ids=PaperId(doi="10.1000/accept-paper-1"),
        title="Accept Paper",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/accept-paper-1",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(paper))

    app.dependency_overrides[get_memory_store] = lambda: store
    client = TestClient(app)

    response = client.post("/papers/accept-paper-1/accept")

    assert response.status_code == 200
    assert response.json() == {"paper_id": "accept-paper-1", "status": "accepted"}

    candidates = client.get("/papers/candidates")
    assert candidates.status_code == 200
    assert candidates.json()[0]["paper_id"] == "accept-paper-1"
    assert candidates.json()[0]["status"] == "accepted"

    app.dependency_overrides.clear()


def test_accept_paper_returns_404_for_unknown_paper(tmp_path):
    test_db = tmp_path / "api-accept-missing.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    client = TestClient(app)

    response = client.post("/papers/missing-paper/accept")

    assert response.status_code == 404

    app.dependency_overrides.clear()


def test_embed_updates_uploaded_paper_to_chunked_and_persists_chunks(tmp_path):
    test_db = tmp_path / "api-embed.sqlite3"
    upload_dir = tmp_path / "uploads"
    store = get_memory_store(str(test_db))
    paper = PaperMetadata(
        paper_id="embed-paper-1",
        source_ids=PaperId(doi="10.1000/embed-paper-1"),
        title="Embed Paper",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/embed-paper-1",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(paper))
    pdf_path = KnowledgeBase(upload_dir=str(upload_dir)).save_pdf(
        paper_id=paper.paper_id,
        filename="paper.pdf",
        content=b"%PDF-1.4 fake pdf",
    )
    store.update_paper_status(paper.paper_id, "uploaded", pdf_path=pdf_path)

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_knowledge_base] = lambda: FakeKnowledgeBase()
    client = TestClient(app)

    response = client.post("/papers/embed-paper-1/embed")

    assert response.status_code == 200
    assert response.json() == {
        "paper_id": "embed-paper-1",
        "status": "chunked",
        "pdf_path": pdf_path,
        "chunk_count": 2,
    }

    candidates = client.get("/papers/candidates")
    assert candidates.status_code == 200
    assert candidates.json()[0]["paper_id"] == "embed-paper-1"
    assert candidates.json()[0]["status"] == "chunked"
    assert candidates.json()[0]["pdf_path"] == pdf_path
    assert [chunk["text"] for chunk in store.list_knowledge_chunks("embed-paper-1")] == [
        "Phase 2C ext",
        "racted text for chunking.",
    ]

    app.dependency_overrides.clear()


def test_embed_returns_400_for_paper_that_is_not_uploaded(tmp_path):
    test_db = tmp_path / "api-embed-not-uploaded.sqlite3"
    store = get_memory_store(str(test_db))
    paper = PaperMetadata(
        paper_id="embed-paper-2",
        source_ids=PaperId(doi="10.1000/embed-paper-2"),
        title="Embed Paper Pending Upload",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/embed-paper-2",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(paper))

    app.dependency_overrides[get_memory_store] = lambda: store
    client = TestClient(app)

    response = client.post("/papers/embed-paper-2/embed")

    assert response.status_code == 400

    app.dependency_overrides.clear()


def test_embed_returns_404_for_unknown_paper(tmp_path):
    test_db = tmp_path / "api-embed-missing.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    client = TestClient(app)

    response = client.post("/papers/missing-paper/embed")

    assert response.status_code == 404

    app.dependency_overrides.clear()


def test_embed_returns_400_for_uploaded_paper_with_missing_pdf_path(tmp_path):
    test_db = tmp_path / "api-embed-missing-pdf.sqlite3"
    store = get_memory_store(str(test_db))
    paper = PaperMetadata(
        paper_id="embed-paper-missing-pdf",
        source_ids=PaperId(doi="10.1000/embed-paper-missing-pdf"),
        title="Embed Missing PDF",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/embed-paper-missing-pdf",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(paper))
    store.update_paper_status(paper.paper_id, "uploaded")

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_knowledge_base] = lambda: FakeKnowledgeBase()
    client = TestClient(app)

    response = client.post("/papers/embed-paper-missing-pdf/embed")

    assert response.status_code == 400
    assert store.get_paper(paper.paper_id)["status"] == "uploaded"
    assert store.list_knowledge_chunks(paper.paper_id) == []

    app.dependency_overrides.clear()


def test_embed_keeps_uploaded_status_when_extraction_fails(tmp_path):
    test_db = tmp_path / "api-embed-extract-fail.sqlite3"
    upload_dir = tmp_path / "uploads"
    store = get_memory_store(str(test_db))
    paper = PaperMetadata(
        paper_id="embed-paper-fail",
        source_ids=PaperId(doi="10.1000/embed-paper-fail"),
        title="Embed Failure Paper",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/embed-paper-fail",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(paper))
    pdf_path = KnowledgeBase(upload_dir=str(upload_dir)).save_pdf(
        paper_id=paper.paper_id,
        filename="paper.pdf",
        content=b"%PDF-1.4 fake pdf",
    )
    store.update_paper_status(paper.paper_id, "uploaded", pdf_path=pdf_path)

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_knowledge_base] = lambda: FakeKnowledgeBase(should_fail=True)
    client = TestClient(app)

    response = client.post("/papers/embed-paper-fail/embed")

    assert response.status_code == 400
    assert store.get_paper(paper.paper_id)["status"] == "uploaded"
    assert store.list_knowledge_chunks(paper.paper_id) == []

    app.dependency_overrides.clear()


def test_embed_rebuild_overwrites_old_chunks_for_uploaded_paper(tmp_path):
    test_db = tmp_path / "api-embed-rebuild.sqlite3"
    upload_dir = tmp_path / "uploads"
    store = get_memory_store(str(test_db))
    paper = PaperMetadata(
        paper_id="embed-paper-rebuild",
        source_ids=PaperId(doi="10.1000/embed-paper-rebuild"),
        title="Embed Rebuild Paper",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/embed-paper-rebuild",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(paper))
    pdf_path = KnowledgeBase(upload_dir=str(upload_dir)).save_pdf(
        paper_id=paper.paper_id,
        filename="paper.pdf",
        content=b"%PDF-1.4 fake pdf",
    )
    store.update_paper_status(paper.paper_id, "uploaded", pdf_path=pdf_path)
    store.insert_knowledge_chunks(
        paper.paper_id,
        [{"chunk_index": 0, "text": "old chunk", "chunk_hash": "old-hash", "vector_ref": None}],
    )

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_knowledge_base] = lambda: FakeKnowledgeBase(
        extracted_text="new chunk payload for rebuild",
    )
    client = TestClient(app)

    response = client.post("/papers/embed-paper-rebuild/embed")

    assert response.status_code == 200
    assert response.json()["status"] == "chunked"
    assert [chunk["text"] for chunk in store.list_knowledge_chunks(paper.paper_id)] == [
        "new chunk pa",
        "yload for rebuild",
    ]

    app.dependency_overrides.clear()


def test_upload_pdf_returns_404_for_unknown_paper(tmp_path):
    test_db = tmp_path / "api-upload-missing.sqlite3"
    upload_dir = tmp_path / "uploads"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    app.dependency_overrides[get_knowledge_base] = lambda: KnowledgeBase(upload_dir=str(upload_dir))
    client = TestClient(app)

    response = client.post(
        "/papers/missing-paper/upload_pdf",
        files={"file": ("paper.pdf", b"%PDF-1.4 fake pdf", "application/pdf")},
    )

    assert response.status_code == 404
    assert not upload_dir.exists()

    app.dependency_overrides.clear()
