from pathlib import Path

from fastapi.testclient import TestClient

import main
from config import config
from graph.builder import build_paper_discovery_graph
from main import (
    app,
    get_answer_generator,
    get_embedding_service,
    get_knowledge_base,
    get_knowledge_qa_service,
    get_memory_store,
    get_paper_discovery_graph,
    get_research_workflow_service,
    get_vector_store_service,
)
from services.embedding_service import FakeEmbeddingService
from services.knowledge_base import KnowledgeBase
from services.query_rewriter import QueryRewriter
from services.schemas import JudgeResult, KnowledgeAnswerResponse, KnowledgeAnswerSource, PaperId, PaperMetadata
from services.vector_store import FakeVectorStoreService
from services.answer_service import FakeGroundedAnswerGenerator
from services.research_workflow import ResearchWorkflowService


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
    def judge(self, query: str, paper: PaperMetadata) -> JudgeResult:
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


class FailingEmbeddingService(FakeEmbeddingService):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise ValueError("fake embedding failure")


class FailingVectorStoreService(FakeVectorStoreService):
    def upsert_chunks(self, chunks: list[dict], embeddings: list[list[float]]) -> list[str]:
        raise ValueError("fake vector store failure")


class EmptyVectorRefStoreService(FakeVectorStoreService):
    def upsert_chunks(self, chunks: list[dict], embeddings: list[list[float]]) -> list[str]:
        vector_refs = super().upsert_chunks(chunks, embeddings)
        vector_refs[-1] = ""
        return vector_refs


class FakeKnowledgeQAService:
    def __init__(self, response: KnowledgeAnswerResponse | None = None):
        self.response = response or KnowledgeAnswerResponse(
            question="lightweight graph reconstruction",
            answer="Knowledge answer",
            sources=[
                KnowledgeAnswerSource(
                    paper_id="knowledge-paper-1",
                    title="Knowledge Paper",
                    chunk_index=0,
                    distance=0.1,
                    text="embedded chunk",
                    vector_ref="chroma:research_chunks:knowledge-paper-1:0:hash-0",
                )
            ],
            mode="deterministic",
        )

    def answer(self, question: str, top_k: int = 5) -> KnowledgeAnswerResponse:
        return self.response.model_copy(update={"question": question})


def override_store_with_path(test_db):
    return lambda: get_memory_store(str(test_db))


def test_health_endpoint_returns_ok():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_endpoint_allows_vite_cors_origin():
    client = TestClient(app)

    response = client.get("/health", headers={"Origin": "http://127.0.0.1:5173"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_get_paper_judge_returns_mock_provider_by_default():
    judge = main.get_paper_judge()

    assert judge.provider_name == "mock"


def test_get_paper_judge_builds_deepseek_provider_from_explicit_config(monkeypatch):
    original_provider = config.paper_judge_provider
    original_model = config.paper_judge_model
    original_api_key = config.deepseek_api_key
    original_base_url = config.deepseek_base_url

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, prompt: str):
            return '{"decision":"accept","llm_relevance_score":0.8,"quality_score":0.7,"reason":"ok","tags":["deepseek"]}'

    try:
        monkeypatch.setattr(main, "ChatOpenAI", FakeChatOpenAI)
        config.paper_judge_provider = "deepseek"
        config.paper_judge_model = "deepseek-reasoner"
        config.deepseek_api_key = "test-key"
        config.deepseek_base_url = "https://example.invalid/v1"

        judge = main.get_paper_judge()

        assert judge.provider_name == "deepseek"
        assert isinstance(judge.llm_client, FakeChatOpenAI)
        assert judge.llm_client.kwargs["model"] == "deepseek-reasoner"
        assert judge.llm_client.kwargs["api_key"] == "test-key"
        assert judge.llm_client.kwargs["base_url"] == "https://example.invalid/v1"
    finally:
        config.paper_judge_provider = original_provider
        config.paper_judge_model = original_model
        config.deepseek_api_key = original_api_key
        config.deepseek_base_url = original_base_url


def test_knowledge_search_returns_retrieved_results_for_embedded_chunks(tmp_path):
    test_db = tmp_path / "api-knowledge.sqlite3"
    store = get_memory_store(str(test_db))
    vector_store = FakeVectorStoreService()
    paper = PaperMetadata(
        paper_id="knowledge-paper-1",
        source_ids=PaperId(doi="10.1000/knowledge-paper-1"),
        title="Knowledge Paper",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/knowledge-paper-1",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))
    store.update_paper_status(paper.paper_id, "embedded", pdf_path="/tmp/knowledge-paper.pdf")
    vector_ref = vector_store.upsert_chunks(
        [
            {
                "chunk_uid": "knowledge-paper-1:0:hash-0",
                "paper_id": paper.paper_id,
                "chunk_index": 0,
                "text": "graph reconstruction knowledge chunk",
            }
        ],
        embeddings=[FakeEmbeddingService().embed_texts(["graph reconstruction knowledge chunk"])[0]],
    )[0]
    store.insert_knowledge_chunks(
        paper.paper_id,
        [{"chunk_index": 0, "text": "graph reconstruction knowledge chunk", "chunk_hash": "hash-0", "vector_ref": vector_ref}],
    )

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_store_service] = lambda: vector_store
    client = TestClient(app)

    response = client.post("/knowledge/search", json={"query": "graph reconstruction", "top_k": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "graph reconstruction"
    assert body["results"][0]["paper_id"] == "knowledge-paper-1"
    assert body["results"][0]["vector_ref"] == vector_ref

    app.dependency_overrides.clear()


def test_knowledge_search_returns_empty_results_when_no_embedded_chunks_exist(tmp_path):
    test_db = tmp_path / "api-knowledge-empty.sqlite3"
    store = get_memory_store(str(test_db))

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_store_service] = lambda: FakeVectorStoreService()
    client = TestClient(app)

    response = client.post("/knowledge/search", json={"query": "graph reconstruction"})

    assert response.status_code == 200
    assert response.json()["results"] == []

    app.dependency_overrides.clear()


def test_knowledge_search_rejects_blank_query(tmp_path):
    test_db = tmp_path / "api-knowledge-blank.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_store_service] = lambda: FakeVectorStoreService()
    client = TestClient(app)

    response = client.post("/knowledge/search", json={"query": "   "})

    assert response.status_code == 400

    app.dependency_overrides.clear()


def test_knowledge_answer_returns_answer_and_sources_for_embedded_chunks(tmp_path):
    test_db = tmp_path / "api-knowledge-answer.sqlite3"
    store = get_memory_store(str(test_db))
    vector_store = FakeVectorStoreService()
    paper = PaperMetadata(
        paper_id="knowledge-answer-paper-1",
        source_ids=PaperId(doi="10.1000/knowledge-answer-paper-1"),
        title="Knowledge Answer Paper",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/knowledge-answer-paper-1",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))
    store.update_paper_status(paper.paper_id, "embedded", pdf_path="/tmp/knowledge-answer-paper.pdf")
    vector_ref = vector_store.upsert_chunks(
        [
            {
                "chunk_uid": "knowledge-answer-paper-1:0:hash-0",
                "paper_id": paper.paper_id,
                "chunk_index": 0,
                "text": "graph reconstruction grounded answer chunk",
            }
        ],
        embeddings=[FakeEmbeddingService().embed_texts(["graph reconstruction grounded answer chunk"])[0]],
    )[0]
    store.insert_knowledge_chunks(
        paper.paper_id,
        [{"chunk_index": 0, "text": "graph reconstruction grounded answer chunk", "chunk_hash": "hash-0", "vector_ref": vector_ref}],
    )

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_store_service] = lambda: vector_store
    app.dependency_overrides[get_answer_generator] = lambda: FakeGroundedAnswerGenerator()
    client = TestClient(app)

    response = client.post("/knowledge/answer", json={"question": "How do I answer graph reconstruction questions?"})

    assert response.status_code == 200
    body = response.json()
    assert body["question"] == "How do I answer graph reconstruction questions?"
    assert body["mode"] == "deterministic"
    assert body["sources"][0]["paper_id"] == "knowledge-answer-paper-1"
    assert body["sources"][0]["vector_ref"] == vector_ref

    app.dependency_overrides.clear()


def test_knowledge_answer_returns_fallback_when_no_results_exist(tmp_path):
    test_db = tmp_path / "api-knowledge-answer-empty.sqlite3"
    store = get_memory_store(str(test_db))

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_store_service] = lambda: FakeVectorStoreService()
    app.dependency_overrides[get_answer_generator] = lambda: FakeGroundedAnswerGenerator()
    client = TestClient(app)

    response = client.post("/knowledge/answer", json={"question": "unknown topic"})

    assert response.status_code == 200
    assert response.json()["answer"] == "No relevant knowledge chunks were found."
    assert response.json()["sources"] == []

    app.dependency_overrides.clear()


def test_knowledge_answer_rejects_blank_question(tmp_path):
    test_db = tmp_path / "api-knowledge-answer-blank.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_store_service] = lambda: FakeVectorStoreService()
    app.dependency_overrides[get_answer_generator] = lambda: FakeGroundedAnswerGenerator()
    client = TestClient(app)

    response = client.post("/knowledge/answer", json={"question": "   "})

    assert response.status_code == 400

    app.dependency_overrides.clear()


def test_research_query_returns_discovery_and_knowledge_sections(tmp_path):
    test_db = tmp_path / "api-research-query.sqlite3"
    store = get_memory_store(str(test_db))
    workflow = ResearchWorkflowService(
        discovery_graph=FakeGraph(store),
        knowledge_qa_service=FakeKnowledgeQAService(),
    )

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_research_workflow_service] = lambda: workflow
    client = TestClient(app)

    response = client.post("/research/query", json={"query": "lightweight graph reconstruction", "top_k": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "lightweight graph reconstruction"
    assert body["mode"] == "basic"
    assert body["discovery"]["enabled"] is True
    assert body["discovery"]["candidates"][0]["paper"]["paper_id"] == "api-paper-1"
    assert body["knowledge"]["enabled"] is True
    assert body["knowledge"]["answer"] == "Knowledge answer"
    assert body["knowledge"]["sources"][0]["paper_id"] == "knowledge-paper-1"

    app.dependency_overrides.clear()


def test_research_query_rejects_blank_query(tmp_path):
    test_db = tmp_path / "api-research-query-blank.sqlite3"
    store = get_memory_store(str(test_db))
    workflow = ResearchWorkflowService(
        discovery_graph=FakeGraph(store),
        knowledge_qa_service=FakeKnowledgeQAService(),
    )

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_research_workflow_service] = lambda: workflow
    client = TestClient(app)

    response = client.post("/research/query", json={"query": "   "})

    assert response.status_code == 400

    app.dependency_overrides.clear()


def test_research_query_rejects_when_both_sections_disabled(tmp_path):
    test_db = tmp_path / "api-research-query-disabled.sqlite3"
    store = get_memory_store(str(test_db))
    workflow = ResearchWorkflowService(
        discovery_graph=FakeGraph(store),
        knowledge_qa_service=FakeKnowledgeQAService(),
    )

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_research_workflow_service] = lambda: workflow
    client = TestClient(app)

    response = client.post(
        "/research/query",
        json={
            "query": "lightweight graph reconstruction",
            "include_discovery": False,
            "include_knowledge": False,
        },
    )

    assert response.status_code == 400

    app.dependency_overrides.clear()


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


def experiment_log_payload():
    return {
        "task": "defect classification",
        "model": "1D-CNN",
        "dataset": "bearing fault dataset",
        "metric_problem": "minority class PRAUC is low",
        "tried_methods": ["class weighting", "focal loss"],
        "observation": "recall improves but precision collapses",
        "goal": "improve PRAUC without making model too heavy",
        "tags": ["imbalanced-learning"],
    }


def test_experiment_logs_endpoint_saves_and_lists_structured_logs(tmp_path):
    test_db = tmp_path / "api-experiment-logs.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    client = TestClient(app)

    response = client.post("/experiments/logs", json=experiment_log_payload())
    assert response.status_code == 200
    assert response.json()["id"] == 1

    logs = client.get("/experiments/logs")
    assert logs.status_code == 200
    assert logs.json()[0]["task"] == "defect classification"
    assert logs.json()[0]["tried_methods"] == ["class weighting", "focal loss"]

    app.dependency_overrides.clear()


def test_ideas_recommend_endpoint_returns_deterministic_no_source_ideas(tmp_path):
    test_db = tmp_path / "api-ideas.sqlite3"
    store = get_memory_store(str(test_db))

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_store_service] = lambda: FakeVectorStoreService()
    client = TestClient(app)

    response = client.post(
        "/ideas/recommend",
        json={
            "experiment_log": experiment_log_payload(),
            "save_log": True,
            "include_discovery": False,
            "top_k": 5,
            "idea_count": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["log_id"] == 1
    assert body["mode"] == "deterministic"
    assert body["discovery"]["enabled"] is False
    assert len(body["ideas"]) == 3
    assert body["ideas"][0]["supporting_evidence"] == []

    app.dependency_overrides.clear()


def test_ideas_recommend_rejects_blank_required_fields(tmp_path):
    test_db = tmp_path / "api-ideas-invalid.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    client = TestClient(app)

    payload = experiment_log_payload()
    payload["task"] = ""

    response = client.post(
        "/ideas/recommend",
        json={"experiment_log": payload},
    )

    assert response.status_code == 422

    app.dependency_overrides.clear()


def test_candidates_endpoint_returns_empty_list(tmp_path):
    test_db = tmp_path / "api.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    client = TestClient(app)

    response = client.get("/papers/candidates")

    assert response.status_code == 200
    assert response.json() == []

    app.dependency_overrides.clear()


def test_memory_candidate_refresh_list_accept_and_semantic_list(tmp_path):
    test_db = tmp_path / "api-memory.sqlite3"
    store = get_memory_store(str(test_db))
    for _ in range(3):
        store.add_experiment_log_entry(
            {
                "task": "defect classification",
                "model": "1D-CNN",
                "dataset": "bearing fault dataset",
                "metric_problem": "minority PRAUC is low",
                "tried_methods": ["focal loss"],
                "observation": "recall improves but precision collapses",
                "goal": "improve PRAUC without making model too heavy",
                "tags": ["lightweight"],
            }
        )

    app.dependency_overrides[get_memory_store] = lambda: store
    client = TestClient(app)

    refresh = client.post("/memory/candidates/refresh")
    assert refresh.status_code == 200
    assert refresh.json()

    candidates = client.get("/memory/candidates")
    assert candidates.status_code == 200
    candidate_id = candidates.json()[0]["id"]

    accepted = client.post(f"/memory/candidates/{candidate_id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "confirmed"

    semantic = client.get("/memory/semantic")
    assert semantic.status_code == 200
    assert semantic.json()

    app.dependency_overrides.clear()


def test_memory_candidate_reject_does_not_create_semantic_memory(tmp_path):
    test_db = tmp_path / "api-memory-reject.sqlite3"
    store = get_memory_store(str(test_db))
    candidate_id = store.upsert_memory_candidate(
        {
            "candidate_type": "semantic_proposal",
            "category": "experiment_target",
            "subject": "defect classification",
            "predicate": "uses_object",
            "object": "focal loss",
            "summary": "defect classification repeatedly uses focal loss",
            "source_log_ids": [1, 2, 3],
            "evidence_count": 3,
            "score": 0.8,
            "status": "pending",
        }
    )

    app.dependency_overrides[get_memory_store] = lambda: store
    client = TestClient(app)

    rejected = client.post(f"/memory/candidates/{candidate_id}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    semantic = client.get("/memory/semantic")
    assert semantic.status_code == 200
    assert semantic.json() == []

    app.dependency_overrides.clear()


def test_memory_semantic_archive_hides_entry_from_default_list(tmp_path):
    test_db = tmp_path / "api-memory-archive.sqlite3"
    store = get_memory_store(str(test_db))
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
    semantic_id = store.upsert_semantic_memory_from_candidate(store.get_memory_candidate(candidate_id))

    app.dependency_overrides[get_memory_store] = lambda: store
    client = TestClient(app)

    archived = client.post(f"/memory/semantic/{semantic_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    semantic = client.get("/memory/semantic")
    assert semantic.status_code == 200
    assert semantic.json() == []

    archived_list = client.get("/memory/semantic?status=archived")
    assert archived_list.status_code == 200
    assert archived_list.json()[0]["id"] == semantic_id

    app.dependency_overrides.clear()


def test_search_returns_candidates_without_persisting_to_sqlite(tmp_path):
    test_db = tmp_path / "api.sqlite3"
    store = get_memory_store(str(test_db))

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_paper_discovery_graph] = lambda: build_paper_discovery_graph(
        search_service=FakeSearchService(),
        judge=FakeJudge(),
        memory_store=store,
        query_rewriter=QueryRewriter(),
    )
    client = TestClient(app)

    response = client.post("/search", json={"mode": "basic", "query": "graph reconstruction"})

    assert response.status_code == 200
    body = response.json()
    assert body[0]["paper"]["paper_id"] == "api-graph-reconstruction"

    candidates = client.get("/papers/candidates")
    assert candidates.status_code == 200
    assert candidates.json() == []

    summary = client.get("/memory/summary")
    assert summary.status_code == 200
    assert summary.json()["candidate_count"] == 0

    app.dependency_overrides.clear()


def test_advanced_search_uses_deterministic_memory_context_rewriting(tmp_path):
    test_db = tmp_path / "api-advanced.sqlite3"
    store = get_memory_store(str(test_db))
    store.add_experiment_log(
        "legacy model is too heavy and needs better interpretability",
        tags=["legacy"],
    )
    store.add_experiment_log_entry(
        {
            "task": "graph reconstruction",
            "model": "compact GNN",
            "dataset": "defect graph benchmark",
            "metric_problem": "latency is too high",
            "tried_methods": ["pruning"],
            "observation": "need better interpretability while keeping the model light",
            "goal": "find lightweight interpretable graph reconstruction methods",
            "tags": ["lightweight", "interpretability"],
        }
    )

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
    assert summary.json()["candidate_count"] == 0

    app.dependency_overrides.clear()


def test_research_query_discovery_returns_candidates_without_persisting_to_sqlite(tmp_path):
    test_db = tmp_path / "api-research-query-no-persist.sqlite3"
    store = get_memory_store(str(test_db))
    workflow = ResearchWorkflowService(
        discovery_graph=build_paper_discovery_graph(
            search_service=FakeSearchService(),
            judge=FakeJudge(),
            memory_store=store,
            query_rewriter=QueryRewriter(),
        ),
        knowledge_qa_service=FakeKnowledgeQAService(),
    )

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_research_workflow_service] = lambda: workflow
    client = TestClient(app)

    response = client.post(
        "/research/query",
        json={
            "query": "graph reconstruction",
            "include_discovery": True,
            "include_knowledge": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["discovery"]["candidates"][0]["paper"]["paper_id"] == "api-graph-reconstruction"
    assert client.get("/papers/candidates").json() == []

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
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))

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


def test_accept_existing_paper_without_body_updates_status_as_compatibility_path(tmp_path):
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
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))

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


def test_accept_discovery_candidate_with_payload_persists_and_accepts_main_path(tmp_path):
    test_db = tmp_path / "api-accept-new.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    client = TestClient(app)

    response = client.post(
        "/papers/accept-paper-2/accept",
        json={
            "paper": {
                "paper_id": "accept-paper-2",
                "source_ids": {"doi": "10.1000/accept-paper-2"},
                "title": "Accept New Paper",
                "authors": ["Tester"],
                "abstract": "Useful abstract.",
                "doi": "10.1000/accept-paper-2",
                "source": "test",
            },
            "judgement": {
                "decision": "accept",
                "reason": "Relevant",
                "llm_relevance_score": 0.9,
                "embedding_relevance_score": 0.8,
                "quality_score": 0.7,
                "novelty_score": 1.0,
                "final_score": 0.85,
                "tags": ["fake"],
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"paper_id": "accept-paper-2", "status": "accepted"}

    candidates = client.get("/papers/candidates")
    assert candidates.status_code == 200
    assert candidates.json()[0]["paper_id"] == "accept-paper-2"
    assert candidates.json()[0]["status"] == "accepted"
    assert candidates.json()[0]["judgement"]["decision"] == "accept"

    app.dependency_overrides.clear()


def test_accept_missing_paper_without_payload_is_rejected_as_invalid_path(tmp_path):
    test_db = tmp_path / "api-accept-missing.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    client = TestClient(app)

    response = client.post("/papers/missing-paper/accept")

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "paper not found: missing-paper; paper metadata is required to save a new discovery candidate. "
        "Provide paper and optional judgement payload."
    )

    app.dependency_overrides.clear()


def test_accept_rejects_mismatched_path_and_body_paper_id(tmp_path):
    test_db = tmp_path / "api-accept-mismatch.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    client = TestClient(app)

    response = client.post(
        "/papers/path-paper/accept",
        json={
            "paper": {
                "paper_id": "body-paper",
                "source_ids": {"doi": "10.1000/body-paper"},
                "title": "Body Paper",
                "authors": ["Tester"],
                "abstract": "Useful abstract.",
                "doi": "10.1000/body-paper",
                "source": "test",
            },
            "judgement": {
                "decision": "accept",
                "reason": "Relevant",
                "llm_relevance_score": 0.9,
                "embedding_relevance_score": 0.8,
                "quality_score": 0.7,
                "novelty_score": 1.0,
                "final_score": 0.85,
                "tags": ["fake"],
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "paper_id mismatch: path=path-paper body=body-paper"

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
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))
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
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))

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
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))
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
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))
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
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))
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


def test_embed_updates_chunked_paper_to_embedded_and_writes_vector_refs(tmp_path):
    test_db = tmp_path / "api-embed-vectors.sqlite3"
    store = get_memory_store(str(test_db))
    paper = PaperMetadata(
        paper_id="chunked-paper-1",
        source_ids=PaperId(doi="10.1000/chunked-paper-1"),
        title="Chunked Paper",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/chunked-paper-1",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))
    store.update_paper_status(paper.paper_id, "chunked", pdf_path="/tmp/chunked-paper.pdf")
    store.insert_knowledge_chunks(
        paper.paper_id,
        [
            {"chunk_index": 0, "text": "chunk a", "chunk_hash": "hash-a", "vector_ref": None},
            {"chunk_index": 1, "text": "chunk b", "chunk_hash": "hash-b", "vector_ref": None},
        ],
    )

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_store_service] = lambda: FakeVectorStoreService()
    client = TestClient(app)

    response = client.post("/papers/chunked-paper-1/embed")

    assert response.status_code == 200
    assert response.json() == {
        "paper_id": "chunked-paper-1",
        "status": "embedded",
        "vector_ref_count": 2,
    }
    assert store.get_paper(paper.paper_id)["status"] == "embedded"
    assert [chunk["vector_ref"] for chunk in store.list_knowledge_chunks(paper.paper_id)] == [
        "chroma:research_chunks:chunked-paper-1:0:hash-a",
        "chroma:research_chunks:chunked-paper-1:1:hash-b",
    ]

    app.dependency_overrides.clear()


def test_embed_returns_400_for_chunked_paper_with_no_chunks(tmp_path):
    test_db = tmp_path / "api-embed-no-chunks.sqlite3"
    store = get_memory_store(str(test_db))
    paper = PaperMetadata(
        paper_id="chunked-paper-no-chunks",
        source_ids=PaperId(doi="10.1000/chunked-paper-no-chunks"),
        title="Chunked Paper No Chunks",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/chunked-paper-no-chunks",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))
    store.update_paper_status(paper.paper_id, "chunked", pdf_path="/tmp/chunked-paper.pdf")

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_store_service] = lambda: FakeVectorStoreService()
    client = TestClient(app)

    response = client.post("/papers/chunked-paper-no-chunks/embed")

    assert response.status_code == 400
    assert store.get_paper(paper.paper_id)["status"] == "chunked"

    app.dependency_overrides.clear()


def test_embed_keeps_chunked_status_when_embedding_fails(tmp_path):
    test_db = tmp_path / "api-embed-embedding-fail.sqlite3"
    store = get_memory_store(str(test_db))
    paper = PaperMetadata(
        paper_id="chunked-paper-embedding-fail",
        source_ids=PaperId(doi="10.1000/chunked-paper-embedding-fail"),
        title="Chunked Paper Embedding Fail",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/chunked-paper-embedding-fail",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))
    store.update_paper_status(paper.paper_id, "chunked", pdf_path="/tmp/chunked-paper.pdf")
    store.insert_knowledge_chunks(
        paper.paper_id,
        [{"chunk_index": 0, "text": "chunk a", "chunk_hash": "hash-a", "vector_ref": None}],
    )

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_embedding_service] = lambda: FailingEmbeddingService()
    app.dependency_overrides[get_vector_store_service] = lambda: FakeVectorStoreService()
    client = TestClient(app)

    response = client.post("/papers/chunked-paper-embedding-fail/embed")

    assert response.status_code == 400
    assert store.get_paper(paper.paper_id)["status"] == "chunked"
    assert store.list_knowledge_chunks(paper.paper_id)[0]["vector_ref"] is None

    app.dependency_overrides.clear()


def test_embed_keeps_chunked_status_when_vector_store_write_fails(tmp_path):
    test_db = tmp_path / "api-embed-vector-store-fail.sqlite3"
    store = get_memory_store(str(test_db))
    paper = PaperMetadata(
        paper_id="chunked-paper-vector-store-fail",
        source_ids=PaperId(doi="10.1000/chunked-paper-vector-store-fail"),
        title="Chunked Paper Vector Store Fail",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/chunked-paper-vector-store-fail",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))
    store.update_paper_status(paper.paper_id, "chunked", pdf_path="/tmp/chunked-paper.pdf")
    store.insert_knowledge_chunks(
        paper.paper_id,
        [{"chunk_index": 0, "text": "chunk a", "chunk_hash": "hash-a", "vector_ref": None}],
    )

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_store_service] = lambda: FailingVectorStoreService()
    client = TestClient(app)

    response = client.post("/papers/chunked-paper-vector-store-fail/embed")

    assert response.status_code == 400
    assert store.get_paper(paper.paper_id)["status"] == "chunked"
    assert store.list_knowledge_chunks(paper.paper_id)[0]["vector_ref"] is None

    app.dependency_overrides.clear()


def test_embed_keeps_chunked_status_when_any_vector_ref_is_empty(tmp_path):
    test_db = tmp_path / "api-embed-empty-vector-ref.sqlite3"
    store = get_memory_store(str(test_db))
    paper = PaperMetadata(
        paper_id="chunked-paper-empty-vector-ref",
        source_ids=PaperId(doi="10.1000/chunked-paper-empty-vector-ref"),
        title="Chunked Paper Empty Vector Ref",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/chunked-paper-empty-vector-ref",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))
    store.update_paper_status(paper.paper_id, "chunked", pdf_path="/tmp/chunked-paper.pdf")
    store.insert_knowledge_chunks(
        paper.paper_id,
        [
            {"chunk_index": 0, "text": "chunk a", "chunk_hash": "hash-a", "vector_ref": None},
            {"chunk_index": 1, "text": "chunk b", "chunk_hash": "hash-b", "vector_ref": None},
        ],
    )

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_store_service] = lambda: EmptyVectorRefStoreService()
    client = TestClient(app)

    response = client.post("/papers/chunked-paper-empty-vector-ref/embed")

    assert response.status_code == 400
    assert store.get_paper(paper.paper_id)["status"] == "chunked"
    assert store.has_complete_knowledge_chunk_vector_refs(paper.paper_id) is False

    app.dependency_overrides.clear()


def test_embed_replaces_stale_vector_refs_for_chunked_paper(tmp_path):
    test_db = tmp_path / "api-embed-replace-vector-refs.sqlite3"
    store = get_memory_store(str(test_db))
    vector_store = FakeVectorStoreService()
    paper = PaperMetadata(
        paper_id="chunked-paper-rebuild",
        source_ids=PaperId(doi="10.1000/chunked-paper-rebuild"),
        title="Chunked Paper Rebuild",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/chunked-paper-rebuild",
        source="test",
    )
    store.save_candidate_paper(paper, FakeJudge().judge(query="graph reconstruction", paper=paper))
    store.update_paper_status(paper.paper_id, "chunked", pdf_path="/tmp/chunked-paper.pdf")
    store.insert_knowledge_chunks(
        paper.paper_id,
        [
            {
                "chunk_index": 0,
                "text": "chunk a",
                "chunk_hash": "hash-a",
                "vector_ref": "chroma:research_chunks:stale-uid-a",
            },
            {
                "chunk_index": 1,
                "text": "chunk b",
                "chunk_hash": "hash-b",
                "vector_ref": "chroma:research_chunks:stale-uid-b",
            },
        ],
    )
    vector_store.records["chroma:research_chunks:stale-uid-a"] = {"chunk": {}, "embedding": []}
    vector_store.records["chroma:research_chunks:stale-uid-b"] = {"chunk": {}, "embedding": []}

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_store_service] = lambda: vector_store
    client = TestClient(app)

    response = client.post("/papers/chunked-paper-rebuild/embed")

    assert response.status_code == 200
    assert response.json()["status"] == "embedded"
    assert "chroma:research_chunks:stale-uid-a" not in vector_store.records
    assert "chroma:research_chunks:stale-uid-b" not in vector_store.records
    assert [chunk["vector_ref"] for chunk in store.list_knowledge_chunks(paper.paper_id)] == [
        "chroma:research_chunks:chunked-paper-rebuild:0:hash-a",
        "chroma:research_chunks:chunked-paper-rebuild:1:hash-b",
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
