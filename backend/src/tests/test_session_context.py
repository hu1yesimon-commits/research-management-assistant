import sqlite3

import pytest

from services.memory_store import MemoryStore
from services.session_context import (
    DeterministicSummaryGenerator,
    SessionContextBuilder,
    SessionSummaryService,
)
from services.session_store import SessionStore


@pytest.fixture
def stores(tmp_path):
    database_path = tmp_path / "memory.sqlite3"
    memory_store = MemoryStore(str(database_path))
    memory_store.initialize()
    return SessionStore(database_path), memory_store


def _complete_turn(store, number):
    turn = store.start_turn(
        "default", f"request-{number}", {"text": f"user turn {number}"}
    )
    store.complete_turn(
        turn.turn_id,
        {"assistant_message": f"assistant turn {number}"},
        {"plan_type": "direct_reply"},
    )
    return turn.turn_id


def _insert_semantic_memory(memory_store, *, summary, status):
    with sqlite3.connect(memory_store.database_path) as connection:
        connection.execute(
            """
            INSERT INTO semantic_memory (
                category, subject, predicate, object, summary, confidence,
                support_count, supporting_log_ids_json, status,
                last_confirmed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "research_topic",
                summary,
                "focuses_on",
                "graph reconstruction",
                summary,
                0.9,
                1,
                "[]",
                status,
                "2026-07-01T00:00:00+00:00",
                "2026-07-01T00:00:00+00:00",
                "2026-07-01T00:00:00+00:00",
            ),
        )


def test_context_uses_summary_and_only_six_recent_completed_turns(stores):
    session_store, memory_store = stores
    oldest_turn = _complete_turn(session_store, 1)
    for number in range(2, 8):
        _complete_turn(session_store, number)
    messages = session_store.list_messages("default")
    session_store.update_session_summary(
        "default", "older research summary", messages[1].id
    )

    context = SessionContextBuilder(session_store, memory_store).build("default")

    assert context.session_summary == "older research summary"
    assert len({message.turn_id for message in context.recent_messages}) == 6
    assert oldest_turn not in {message.turn_id for message in context.recent_messages}
    assert context.current_knowledge == []


def test_context_loads_three_agent_specific_contexts(stores):
    session_store, memory_store = stores
    session_store.upsert_agent_context("default", "leader", "leader context", 1)
    session_store.upsert_agent_context("default", "research", "research context", 2)
    session_store.upsert_agent_context("default", "idea", "idea context", 3)
    session_store.upsert_agent_context("default", "other", "must stay isolated", 4)

    context = SessionContextBuilder(session_store, memory_store).build("default")

    assert context.agent_contexts == {
        "leader": "leader context",
        "research": "research context",
        "idea": "idea context",
    }


def test_context_confirmed_memory_excludes_unreviewed_and_archived(stores):
    session_store, memory_store = stores
    _insert_semantic_memory(memory_store, summary="confirmed fact", status="confirmed")
    _insert_semantic_memory(memory_store, summary="archived fact", status="archived")

    context = SessionContextBuilder(session_store, memory_store).build("default")

    assert "confirmed fact" in context.confirmed_memory
    assert "archived fact" not in context.confirmed_memory
    assert "Recent episodic memory" not in context.confirmed_memory


class RecordingSummaryGenerator:
    def __init__(self, result="new compact summary", error=None):
        self.result = result
        self.error = error
        self.calls = []

    def summarize(self, previous_summary, messages):
        self.calls.append((previous_summary, messages))
        if self.error is not None:
            raise self.error
        return self.result


def test_summary_refresh_waits_until_twelve_unsummarized_messages(stores):
    session_store, _ = stores
    for number in range(1, 6):
        _complete_turn(session_store, number)
    generator = RecordingSummaryGenerator()
    service = SessionSummaryService(session_store, generator, threshold=12)

    assert service.maybe_refresh("default") is False
    assert generator.calls == []
    assert session_store.get_session("default")["summary"] == ""


def test_summary_refresh_at_threshold_replaces_summary_and_advances_boundary(stores):
    session_store, _ = stores
    for number in range(1, 7):
        _complete_turn(session_store, number)
    generator = RecordingSummaryGenerator()

    refreshed = SessionSummaryService(
        session_store, generator, threshold=12
    ).maybe_refresh("default")

    messages = session_store.list_messages("default")
    session = session_store.get_session("default")
    assert refreshed is True
    assert generator.calls[0][0] == ""
    assert [message.id for message in generator.calls[0][1]] == [
        message.id for message in messages
    ]
    assert session["summary"] == "new compact summary"
    assert session["summary_through_message_id"] == messages[-1].id


def test_summary_refresh_respects_existing_summary_boundary(stores):
    session_store, _ = stores
    _complete_turn(session_store, 1)
    old_messages = session_store.list_messages("default")
    session_store.update_session_summary("default", "old summary", old_messages[-1].id)
    for number in range(2, 8):
        _complete_turn(session_store, number)
    generator = RecordingSummaryGenerator()

    assert SessionSummaryService(session_store, generator, threshold=12).maybe_refresh(
        "default"
    )

    previous_summary, summarized_messages = generator.calls[0]
    assert previous_summary == "old summary"
    assert len(summarized_messages) == 12
    assert all(message.id > old_messages[-1].id for message in summarized_messages)


def test_summary_generator_failure_preserves_summary_and_boundary(stores):
    session_store, _ = stores
    _complete_turn(session_store, 1)
    old_messages = session_store.list_messages("default")
    session_store.update_session_summary("default", "old summary", old_messages[-1].id)
    for number in range(2, 8):
        _complete_turn(session_store, number)
    generator = RecordingSummaryGenerator(error=RuntimeError("generator unavailable"))

    refreshed = SessionSummaryService(
        session_store, generator, threshold=12
    ).maybe_refresh("default")

    session = session_store.get_session("default")
    assert refreshed is False
    assert session["summary"] == "old summary"
    assert session["summary_through_message_id"] == old_messages[-1].id


def test_deterministic_summary_uses_supported_content_and_bounds_output(stores):
    session_store, _ = stores
    _complete_turn(session_store, 1)
    messages = session_store.list_messages("default")

    summary = DeterministicSummaryGenerator().summarize("previous", messages)

    assert "previous" in summary
    assert "user: user turn 1" in summary
    assert "assistant: assistant turn 1" in summary
    assert len(summary) <= 6000
