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


def test_initialize_creates_structured_experiment_log_entries_table(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    store = MemoryStore(str(db_path))

    store.initialize()

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    connection.close()

    assert "experiment_log_entries" in {row[0] for row in rows}


def test_initialize_creates_memory_candidates_table(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    store = MemoryStore(str(db_path))

    store.initialize()

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    connection.close()

    assert "memory_candidates" in {row[0] for row in rows}


def test_initialize_creates_semantic_memory_table(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    store = MemoryStore(str(db_path))

    store.initialize()

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    connection.close()

    assert "semantic_memory" in {row[0] for row in rows}


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


def test_add_structured_experiment_log_entry_can_be_listed(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    log_id = store.add_experiment_log_entry(
        {
            "task": "defect classification",
            "model": "1D-CNN",
            "dataset": "bearing fault dataset",
            "metric_problem": "minority class PRAUC is low",
            "tried_methods": ["class weighting", "focal loss"],
            "observation": "recall improves but precision collapses",
            "goal": "improve PRAUC without making model too heavy",
            "tags": ["imbalanced-learning", "lightweight"],
        }
    )

    logs = store.list_experiment_log_entries()

    assert log_id > 0
    assert logs[0]["id"] == log_id
    assert logs[0]["task"] == "defect classification"
    assert logs[0]["tried_methods"] == ["class weighting", "focal loss"]
    assert logs[0]["tags"] == ["imbalanced-learning", "lightweight"]
    assert logs[0]["created_at"]


def test_structured_experiment_logs_are_separate_from_legacy_logs(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    store.add_experiment_log("legacy note", tags=["block"])
    store.add_experiment_log_entry(
        {
            "task": "defect classification",
            "model": "1D-CNN",
            "dataset": "bearing fault dataset",
            "metric_problem": "minority class PRAUC is low",
            "tried_methods": [],
            "observation": "recall improves but precision collapses",
            "goal": "improve PRAUC without making model too heavy",
            "tags": [],
        }
    )

    assert store.list_experiment_logs()[0]["content"] == "legacy note"
    assert store.list_experiment_log_entries()[0]["task"] == "defect classification"


def make_memory_candidate(**overrides):
    candidate = {
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
    candidate.update(overrides)
    return candidate


def test_memory_candidate_can_be_inserted_listed_and_round_trips_source_ids(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    candidate_id = store.upsert_memory_candidate(make_memory_candidate())

    candidates = store.list_memory_candidates()

    assert candidate_id > 0
    assert len(candidates) == 1
    assert candidates[0]["id"] == candidate_id
    assert candidates[0]["object"] == "focal loss"
    assert candidates[0]["source_log_ids"] == [1, 2, 3]


def test_memory_candidate_upsert_updates_existing_stable_key(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    first_id = store.upsert_memory_candidate(make_memory_candidate(source_log_ids=[1, 2, 3], score=0.6))
    second_id = store.upsert_memory_candidate(make_memory_candidate(source_log_ids=[1, 2, 3, 4], score=0.9))

    candidates = store.list_memory_candidates()

    assert second_id == first_id
    assert len(candidates) == 1
    assert candidates[0]["source_log_ids"] == [1, 2, 3, 4]
    assert candidates[0]["evidence_count"] == 4
    assert candidates[0]["score"] == 0.9


def test_rejected_memory_candidate_disappears_from_default_pending_list(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    candidate_id = store.upsert_memory_candidate(make_memory_candidate())

    rejected = store.update_memory_candidate_status(candidate_id, "rejected")

    assert rejected["status"] == "rejected"
    assert rejected["reviewed_at"]
    assert store.list_memory_candidates() == []
    assert store.list_memory_candidates(status="rejected")[0]["id"] == candidate_id


def test_semantic_memory_can_be_inserted_from_candidate_and_archived(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    candidate_id = store.upsert_memory_candidate(make_memory_candidate())
    candidate = store.get_memory_candidate(candidate_id)

    semantic_id = store.upsert_semantic_memory_from_candidate(candidate)
    semantic = store.get_semantic_memory(semantic_id)

    assert semantic["status"] == "confirmed"
    assert semantic["supporting_log_ids"] == [1, 2, 3]
    assert store.list_semantic_memory()[0]["id"] == semantic_id

    archived = store.archive_semantic_memory(semantic_id)

    assert archived["status"] == "archived"
    assert store.list_semantic_memory() == []
    assert store.list_semantic_memory(status="archived")[0]["id"] == semantic_id


def test_build_memory_context_includes_confirmed_semantic_before_recent_logs(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    candidate_id = store.upsert_memory_candidate(
        make_memory_candidate(
            category="user_preference",
            subject="user",
            predicate="prefers",
            object="lightweight",
            summary="User repeatedly prefers lightweight approaches.",
        )
    )
    store.upsert_semantic_memory_from_candidate(store.get_memory_candidate(candidate_id))
    store.add_experiment_log_entry(
        {
            "task": "graph reconstruction",
            "model": "GNN",
            "dataset": "citation graph",
            "metric_problem": "interpretability is weak",
            "tried_methods": ["modular loss"],
            "observation": "loss improves stability",
            "goal": "keep the model interpretable",
            "tags": ["interpretability"],
        }
    )

    context = store.build_memory_context()

    semantic_index = context.index("Confirmed semantic memory")
    episodic_index = context.index("Recent episodic memory")
    assert semantic_index < episodic_index
    assert "user prefers lightweight" in context
    assert "graph reconstruction" in context


def test_build_memory_context_uses_recent_three_structured_logs_not_legacy_logs(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    store.add_experiment_log("legacy note should not enter rewrite", tags=["legacy"])

    for index in range(4):
        store.add_experiment_log_entry(
            {
                "task": f"task-{index}",
                "model": f"model-{index}",
                "dataset": f"dataset-{index}",
                "metric_problem": f"metric problem {index}",
                "tried_methods": [f"method-{index}"],
                "observation": f"observation {index}",
                "goal": f"goal {index}",
                "tags": [f"tag-{index}"],
            }
        )

    context = store.build_memory_context()

    assert "legacy note should not enter rewrite" not in context
    assert "Confirmed semantic memory:" in context
    assert "Recent episodic memory:" in context
    assert "task=task-3" in context
    assert "model=model-3" in context
    assert "dataset=dataset-3" in context
    assert "metric_problem=metric problem 3" in context
    assert "tried_methods=method-3" in context
    assert "observation=observation 3" in context
    assert "goal=goal 3" in context
    assert "tags=tag-3" in context
    assert "task-2" in context
    assert "task-1" in context
    assert "task-0" not in context


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


def test_update_knowledge_chunk_vector_refs_by_chunk_index(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    store.insert_knowledge_chunks(
        "paper-1",
        [
            {"chunk_index": 0, "text": "chunk a", "chunk_hash": "hash-a", "vector_ref": None},
            {"chunk_index": 1, "text": "chunk b", "chunk_hash": "hash-b", "vector_ref": None},
        ],
    )

    store.update_knowledge_chunk_vector_refs(
        "paper-1",
        [
            {"chunk_index": 0, "vector_ref": "chroma:research_chunks:paper-1:0:hash-a"},
            {"chunk_index": 1, "vector_ref": "chroma:research_chunks:paper-1:1:hash-b"},
        ],
    )

    assert [chunk["vector_ref"] for chunk in store.list_knowledge_chunks("paper-1")] == [
        "chroma:research_chunks:paper-1:0:hash-a",
        "chroma:research_chunks:paper-1:1:hash-b",
    ]


def test_clear_knowledge_chunk_vector_refs_for_paper(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    store.insert_knowledge_chunks(
        "paper-1",
        [
            {"chunk_index": 0, "text": "chunk a", "chunk_hash": "hash-a", "vector_ref": "ref-a"},
            {"chunk_index": 1, "text": "chunk b", "chunk_hash": "hash-b", "vector_ref": "ref-b"},
        ],
    )

    store.clear_knowledge_chunk_vector_refs("paper-1")

    assert [chunk["vector_ref"] for chunk in store.list_knowledge_chunks("paper-1")] == [None, None]


def test_has_complete_knowledge_chunk_vector_refs_returns_true_only_when_all_chunks_are_non_empty(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    store.insert_knowledge_chunks(
        "paper-1",
        [
            {"chunk_index": 0, "text": "chunk a", "chunk_hash": "hash-a", "vector_ref": None},
            {"chunk_index": 1, "text": "chunk b", "chunk_hash": "hash-b", "vector_ref": None},
        ],
    )

    assert store.has_complete_knowledge_chunk_vector_refs("paper-1") is False

    store.update_knowledge_chunk_vector_refs(
        "paper-1",
        [
            {"chunk_index": 0, "vector_ref": "chroma:research_chunks:paper-1:0:hash-a"},
            {"chunk_index": 1, "vector_ref": ""},
        ],
    )

    assert store.has_complete_knowledge_chunk_vector_refs("paper-1") is False

    store.update_knowledge_chunk_vector_refs(
        "paper-1",
        [{"chunk_index": 1, "vector_ref": "chroma:research_chunks:paper-1:1:hash-b"}],
    )

    assert store.has_complete_knowledge_chunk_vector_refs("paper-1") is True


def test_has_complete_knowledge_chunk_vector_refs_returns_false_for_missing_chunks(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    assert store.has_complete_knowledge_chunk_vector_refs("missing-paper") is False
