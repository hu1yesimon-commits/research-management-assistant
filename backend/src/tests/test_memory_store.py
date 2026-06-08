import sqlite3

from services.memory_store import MemoryStore
from services.schemas import JudgeResult, PaperId, PaperMetadata


def make_paper(paper_id: str, doi: str | None, status_doi: str | None = None) -> PaperMetadata:
    return PaperMetadata(
        paper_id=paper_id,
        source_ids=PaperId(doi=status_doi or doi),
        title=f"Paper {paper_id}",
        authors=["Tester"],
        abstract=f"Abstract for {paper_id}",
        published_date="2026-01-01",
        doi=doi,
        source="test",
    )


def make_judgement(decision: str = "accept") -> JudgeResult:
    return JudgeResult(
        decision=decision,
        reason="Looks relevant",
        llm_relevance_score=0.9,
        embedding_relevance_score=0.8,
        quality_score=0.7,
        novelty_score=0.6,
        final_score=0.75,
        tags=["useful"],
    )


def test_initialize_creates_sqlite_tables(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    store = MemoryStore(str(db_path))

    store.initialize()

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    connection.close()

    assert {row[0] for row in rows} >= {
        "experiment_logs",
        "knowledge_chunks",
        "paper_judgements",
        "papers",
    }


def test_save_candidate_paper_can_be_listed(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    paper = make_paper("paper-1", "https://doi.org/10.1000/Test-DOI")
    judgement = make_judgement()

    store.save_candidate_paper(paper, judgement)
    candidates = store.list_candidate_papers()

    assert len(candidates) == 1
    assert candidates[0]["paper_id"] == "paper-1"
    assert candidates[0]["title"] == "Paper paper-1"
    assert candidates[0]["doi"] == "10.1000/test-doi"
    assert candidates[0]["status"] == "candidate"


def test_add_experiment_log_can_be_listed(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    log_id = store.add_experiment_log("training loss is unstable", tags=["block", "debug"])
    logs = store.list_experiment_logs()

    assert log_id > 0
    assert len(logs) == 1
    assert logs[0]["id"] == log_id
    assert logs[0]["content"] == "training loss is unstable"
    assert logs[0]["tags"] == ["block", "debug"]


def test_build_memory_context_joins_recent_logs(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    store.add_experiment_log("model is too heavy", tags=["block"])
    store.add_experiment_log("need better interpretability", tags=["idea"])

    context = store.build_memory_context()

    assert "idea: need better interpretability" in context
    assert "block: model is too heavy" in context


def test_list_known_dois_only_returns_uploaded_chunked_and_embedded(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    store.save_candidate_paper(make_paper("candidate", "10.1000/candidate"))
    store.save_candidate_paper(make_paper("uploaded", "10.1000/uploaded"))
    store.save_candidate_paper(make_paper("chunked", "10.1000/chunked"))
    store.save_candidate_paper(make_paper("embedded", "https://doi.org/10.1000/EMBEDDED"))

    store.update_paper_status("uploaded", "uploaded", pdf_path="/tmp/uploaded.pdf")
    store.update_paper_status("chunked", "chunked", pdf_path="/tmp/chunked.pdf")
    store.update_paper_status("embedded", "embedded", pdf_path="/tmp/embedded.pdf")

    assert store.list_known_dois() == [
        "10.1000/chunked",
        "10.1000/embedded",
        "10.1000/uploaded",
    ]


def test_insert_and_list_knowledge_chunks_by_paper_id(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    store.insert_knowledge_chunks(
        "paper-1",
        [
            {
                "chunk_index": 0,
                "text": "first chunk",
                "chunk_hash": "hash-1",
                "vector_ref": None,
            },
            {
                "chunk_index": 1,
                "text": "second chunk",
                "chunk_hash": "hash-2",
                "vector_ref": None,
            },
        ],
    )

    assert store.list_knowledge_chunks("paper-1") == [
        {
            "id": 1,
            "paper_id": "paper-1",
            "chunk_index": 0,
            "text": "first chunk",
            "chunk_hash": "hash-1",
            "vector_ref": None,
            "created_at": store.list_knowledge_chunks("paper-1")[0]["created_at"],
        },
        {
            "id": 2,
            "paper_id": "paper-1",
            "chunk_index": 1,
            "text": "second chunk",
            "chunk_hash": "hash-2",
            "vector_ref": None,
            "created_at": store.list_knowledge_chunks("paper-1")[1]["created_at"],
        },
    ]


def test_delete_knowledge_chunks_by_paper_id(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    store.insert_knowledge_chunks(
        "paper-1",
        [{"chunk_index": 0, "text": "chunk", "chunk_hash": "hash-1", "vector_ref": None}],
    )

    store.delete_knowledge_chunks_by_paper("paper-1")

    assert store.list_knowledge_chunks("paper-1") == []


def test_rebuild_knowledge_chunks_replaces_old_rows_for_same_paper(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    store.insert_knowledge_chunks(
        "paper-1",
        [{"chunk_index": 0, "text": "old chunk", "chunk_hash": "old-hash", "vector_ref": None}],
    )

    store.delete_knowledge_chunks_by_paper("paper-1")
    store.insert_knowledge_chunks(
        "paper-1",
        [
            {"chunk_index": 0, "text": "new chunk a", "chunk_hash": "new-hash-a", "vector_ref": None},
            {"chunk_index": 1, "text": "new chunk b", "chunk_hash": "new-hash-b", "vector_ref": None},
        ],
    )

    chunks = store.list_knowledge_chunks("paper-1")
    assert [chunk["text"] for chunk in chunks] == ["new chunk a", "new chunk b"]
    assert all(chunk["vector_ref"] is None for chunk in chunks)
