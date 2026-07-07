import pytest

from services.candidate_lifecycle import (
    CandidateExpiredError,
    CandidateLifecycleService,
    CandidateNotFoundError,
    paper_key,
)
from services.memory_store import MemoryStore
from services.schemas import JudgeResult, PaperId, PaperMetadata
from services.session_store import SessionStore


def make_paper(paper_id: str, doi: str | None = None) -> PaperMetadata:
    return PaperMetadata(
        paper_id=paper_id,
        source_ids=PaperId(doi=doi),
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


def make_candidate(paper_id: str, doi: str | None = None) -> dict:
    return {
        "paper": make_paper(paper_id, doi).model_dump(),
        "judgement": make_judgement().model_dump(),
    }


def make_model_candidate(paper_id: str, doi: str | None = None) -> dict:
    return {
        "paper": make_paper(paper_id, doi),
        "judgement": make_judgement(),
    }


@pytest.fixture
def database_path(tmp_path):
    return tmp_path / "memory.sqlite3"


@pytest.fixture
def memory_store(database_path):
    store = MemoryStore(str(database_path))
    store.initialize()
    return store


@pytest.fixture
def session_store(database_path, memory_store):
    return SessionStore(str(database_path))


@pytest.fixture
def candidate_service(database_path, memory_store):
    return CandidateLifecycleService(str(database_path))


@pytest.fixture
def active_candidate(session_store, candidate_service):
    turn = session_store.start_turn("default", "request-1", {"text": "first"})
    batch = candidate_service.create_batch(
        "default",
        turn.turn_id,
        "first",
        [make_candidate("paper-1", "10.1000/paper-1")],
    )
    return batch.candidates[0]


@pytest.fixture
def expired_candidate(session_store, candidate_service):
    first = session_store.start_turn("default", "request-1", {"text": "first"})
    batch = candidate_service.create_batch(
        "default",
        first.turn_id,
        "first",
        [make_candidate("paper-1", "10.1000/paper-1")],
    )
    session_store.complete_turn(
        first.turn_id,
        {"assistant_message": "done"},
        {"plan_type": "research"},
    )
    session_store.start_turn("default", "request-2", {"text": "second"})
    return batch.candidates[0]


def test_new_turn_expires_previous_unaccepted_candidates(session_store, candidate_service):
    first = session_store.start_turn("default", "turn-1", {"text": "first"})
    candidate_service.create_batch(
        "default",
        first.turn_id,
        "first",
        [make_candidate("paper-1", "10.1000/paper-1")],
    )
    session_store.complete_turn(
        first.turn_id,
        {"assistant_message": "done"},
        {"plan_type": "research"},
    )

    session_store.start_turn("default", "turn-2", {"text": "second"})

    assert candidate_service.list_active("default") == []
    assert candidate_service.get_item_status("doi:10.1000/paper-1") == "expired"


def test_accept_is_transactional_and_idempotent(candidate_service, active_candidate):
    first = candidate_service.accept("default", active_candidate.id)
    second = candidate_service.accept("default", active_candidate.id)

    assert first.status == "accepted"
    assert second == first
    assert candidate_service.get_saved_paper(first.paper_id)["status"] == "accepted"


def test_expired_candidate_cannot_be_accepted(candidate_service, expired_candidate):
    with pytest.raises(CandidateExpiredError):
        candidate_service.accept("default", expired_candidate.id)


def test_unknown_candidate_raises_typed_lookup_error(candidate_service):
    with pytest.raises(CandidateNotFoundError, match="candidate not found: missing"):
        candidate_service.accept("default", "missing")


def test_suppression_keys_include_saved_papers_and_last_expired_batch(
    session_store, candidate_service, memory_store
):
    memory_store.save_candidate_paper(make_paper("saved", "10.1000/saved"))
    memory_store.update_paper_status("saved", "accepted")

    first = session_store.start_turn("default", "request-1", {"text": "first"})
    candidate_service.create_batch(
        "default",
        first.turn_id,
        "first",
        [
            make_candidate("expired", "10.1000/expired"),
            make_candidate("fresh", "10.1000/fresh"),
        ],
    )
    session_store.complete_turn(
        first.turn_id,
        {"assistant_message": "done"},
        {"plan_type": "research"},
    )
    session_store.start_turn("default", "request-2", {"text": "second"})

    assert candidate_service.suppression_keys("default") == {
        "doi:10.1000/saved",
        "doi:10.1000/expired",
        "doi:10.1000/fresh",
    }


def test_filter_fresh_underfills_instead_of_refilling_suppressed_candidates(
    session_store, candidate_service, memory_store
):
    memory_store.save_candidate_paper(make_paper("saved", "10.1000/saved"))
    memory_store.update_paper_status("saved", "accepted")

    ranked = [
        make_candidate("saved", "10.1000/saved"),
        make_candidate("fresh-1", "10.1000/fresh-1"),
        make_candidate("fresh-2", "10.1000/fresh-2"),
    ]

    fresh = candidate_service.filter_fresh("default", ranked, top_k=5)

    assert [paper_key(item["paper"]) for item in fresh] == [
        "doi:10.1000/fresh-1",
        "doi:10.1000/fresh-2",
    ]


def test_filter_and_create_batch_accept_graph_model_candidates(
    session_store, candidate_service
):
    turn = session_store.start_turn("default", "model-candidate", {"text": "search"})
    ranked = [make_model_candidate("model-paper", "10.1000/model-paper")]

    fresh = candidate_service.filter_fresh("default", ranked, top_k=5)
    batch = candidate_service.create_batch("default", turn.turn_id, "search", fresh)

    assert batch.candidates[0].paper_snapshot.paper_id == "model-paper"
    assert batch.candidates[0].paper_key == "doi:10.1000/model-paper"
