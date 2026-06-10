import pytest

from services.memory_extractor import MemoryExtractor
from services.memory_service import MemoryService, MemoryServiceError
from services.memory_store import MemoryStore


def add_repeated_logs(store: MemoryStore):
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


def make_candidate(**overrides):
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


def test_refresh_candidates_creates_pending_semantic_proposals(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    add_repeated_logs(store)
    service = MemoryService(store=store, extractor=MemoryExtractor())

    candidates = service.refresh_candidates()

    assert candidates
    assert all(candidate["status"] == "pending" for candidate in candidates)
    assert any(candidate["object"] == "focal loss" for candidate in candidates)
    assert store.list_memory_candidates()


def test_accept_candidate_creates_confirmed_semantic_memory(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    candidate_id = store.upsert_memory_candidate(make_candidate())
    service = MemoryService(store=store, extractor=MemoryExtractor())

    semantic = service.accept_candidate(candidate_id)

    assert semantic["status"] == "confirmed"
    assert semantic["object"] == "focal loss"
    assert store.get_memory_candidate(candidate_id)["status"] == "accepted"


def test_reject_candidate_does_not_create_semantic_memory(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    candidate_id = store.upsert_memory_candidate(make_candidate())
    service = MemoryService(store=store, extractor=MemoryExtractor())

    rejected = service.reject_candidate(candidate_id)

    assert rejected["status"] == "rejected"
    assert store.list_semantic_memory() == []


def test_accept_only_supports_semantic_proposal_in_mvp(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    candidate_id = store.upsert_memory_candidate(
        make_candidate(
            candidate_type="stale_proposal",
            summary="Review whether this memory is stale.",
        )
    )
    service = MemoryService(store=store, extractor=MemoryExtractor())

    with pytest.raises(MemoryServiceError) as exc:
        service.accept_candidate(candidate_id)

    assert exc.value.status_code == 400
    assert store.list_semantic_memory() == []


def test_accept_reject_and_archive_missing_items_return_404_errors(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    service = MemoryService(store=store, extractor=MemoryExtractor())

    with pytest.raises(MemoryServiceError) as accept_error:
        service.accept_candidate(999)
    with pytest.raises(MemoryServiceError) as reject_error:
        service.reject_candidate(999)
    with pytest.raises(MemoryServiceError) as archive_error:
        service.archive_semantic_memory(999)

    assert accept_error.value.status_code == 404
    assert reject_error.value.status_code == 404
    assert archive_error.value.status_code == 404


def test_refresh_candidates_does_not_archive_confirmed_memory_automatically(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    candidate_id = store.upsert_memory_candidate(
        make_candidate(
            category="user_preference",
            subject="user",
            predicate="prefers",
            object="lightweight",
            summary="User repeatedly prefers lightweight approaches.",
        )
    )
    store.upsert_semantic_memory_from_candidate(store.get_memory_candidate(candidate_id))
    service = MemoryService(store=store, extractor=MemoryExtractor())

    service.refresh_candidates()

    assert store.list_semantic_memory()[0]["status"] == "confirmed"
