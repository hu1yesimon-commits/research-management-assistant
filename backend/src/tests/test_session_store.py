import json
import sqlite3

import pytest

from services.memory_store import MemoryStore
from services.session_store import (
    SessionBusyError,
    SessionStore,
    TurnNotFoundError,
    TurnStateError,
)


@pytest.fixture
def store(tmp_path):
    database_path = tmp_path / "memory.sqlite3"
    MemoryStore(str(database_path)).initialize()
    return SessionStore(str(database_path))


def _complete_turn(store, idempotency_key, text):
    turn = store.start_turn("default", idempotency_key, {"text": text})
    response = {
        "session_id": "default",
        "turn_id": turn.turn_id,
        "status": "completed",
        "assistant_message": f"answer: {text}",
    }
    store.complete_turn(turn.turn_id, response, {"plan_type": "research"})
    return turn.turn_id, response


def test_start_turn_saves_user_message_and_replays_idempotency(store):
    first = store.start_turn("default", "request-1", {"text": "find papers"})
    second = store.start_turn("default", "request-1", {"text": "find papers"})

    assert first.replayed is False
    assert second.replayed is True
    assert second.turn_id == first.turn_id
    assert [message.content["text"] for message in store.list_messages("default")] == [
        "find papers"
    ]


def test_second_running_turn_is_rejected(store):
    store.start_turn("default", "request-1", {"text": "first"})

    with pytest.raises(SessionBusyError):
        store.start_turn("default", "request-2", {"text": "second"})


def test_start_turn_expires_active_candidate_items_before_their_batch(store):
    first_turn_id, _ = _complete_turn(store, "request-1", "first")
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            INSERT INTO candidate_batches (id, session_id, turn_id, query, status, created_at)
            VALUES ('batch-1', 'default', ?, 'first', 'active', '2026-06-30T00:00:00+00:00')
            """,
            (first_turn_id,),
        )
        connection.execute(
            """
            INSERT INTO candidate_items (
                id, batch_id, paper_key, paper_snapshot_json, status, created_at, updated_at
            )
            VALUES (
                'item-1', 'batch-1', 'paper-1', '{}', 'active',
                '2026-06-30T00:00:00+00:00', '2026-06-30T00:00:00+00:00'
            )
            """
        )

    store.start_turn("default", "request-2", {"text": "second"})

    with sqlite3.connect(store.database_path) as connection:
        item = connection.execute(
            "SELECT status, updated_at FROM candidate_items WHERE id = 'item-1'"
        ).fetchone()
        batch = connection.execute(
            "SELECT status, expired_at FROM candidate_batches WHERE id = 'batch-1'"
        ).fetchone()
    assert item[0] == "expired"
    assert item[1] != "2026-06-30T00:00:00+00:00"
    assert batch[0] == "expired"
    assert batch[1] is not None


def test_completion_persists_full_assistant_response_for_replay(store):
    turn = store.start_turn("default", "request-1", {"text": "find papers"})
    response = {
        "session_id": "default",
        "turn_id": turn.turn_id,
        "status": "completed",
        "assistant_message": "found two papers",
        "active_candidates": [{"id": "candidate-1", "title": "Paper"}],
        "errors": [],
    }
    plan = {"plan_type": "research", "steps": [{"agent": "research"}]}

    store.complete_turn(turn.turn_id, response, plan)

    assert store.get_replayed_response("default", turn.turn_id) == response
    persisted_turn = store.get_turn("default", turn.turn_id)
    assert persisted_turn["status"] == "completed"
    assert persisted_turn["plan"] == plan
    assert [message.role for message in store.list_messages("default")] == [
        "user",
        "assistant",
    ]


def test_failure_persists_error_state(store):
    turn = store.start_turn("default", "request-1", {"text": "find papers"})
    error = {"stage": "dispatch", "message": "provider unavailable"}

    store.fail_turn(turn.turn_id, error)

    persisted_turn = store.get_turn("default", turn.turn_id)
    assert persisted_turn["status"] == "failed"
    assert persisted_turn["error"] == error
    assert persisted_turn["completed_at"] is not None
    assert store.get_replayed_response("default", turn.turn_id) is None


def test_completion_rejects_missing_and_non_running_turns(store):
    with pytest.raises(TurnNotFoundError):
        store.complete_turn("missing", {}, {})

    turn_id, _ = _complete_turn(store, "request-1", "first")
    with pytest.raises(TurnStateError):
        store.complete_turn(turn_id, {}, {})


def test_list_messages_paginates_chronologically_with_before_id(store):
    _complete_turn(store, "request-1", "first")
    _complete_turn(store, "request-2", "second")
    _complete_turn(store, "request-3", "third")

    newest_page = store.list_messages("default", limit=2)
    previous_page = store.list_messages(
        "default", before_id=newest_page[0].id, limit=2
    )

    assert [message.id for message in newest_page] == [5, 6]
    assert [message.id for message in previous_page] == [3, 4]
    assert [message.content.get("text") for message in previous_page] == [
        "second",
        None,
    ]


def test_list_recent_turn_messages_uses_newest_completed_turns_in_message_order(store):
    first_turn_id, _ = _complete_turn(store, "request-1", "first")
    failed = store.start_turn("default", "request-2", {"text": "failed"})
    store.fail_turn(failed.turn_id, {"message": "failed"})
    third_turn_id, _ = _complete_turn(store, "request-3", "third")
    fourth_turn_id, _ = _complete_turn(store, "request-4", "fourth")

    messages = store.list_recent_turn_messages("default", turn_limit=2)

    assert [message.turn_id for message in messages] == [
        third_turn_id,
        third_turn_id,
        fourth_turn_id,
        fourth_turn_id,
    ]
    assert [message.id for message in messages] == sorted(message.id for message in messages)
    assert first_turn_id not in {message.turn_id for message in messages}
    assert failed.turn_id not in {message.turn_id for message in messages}


def test_count_unsummarized_messages_and_update_session_summary(store):
    _complete_turn(store, "request-1", "first")
    messages = store.list_messages("default")

    assert store.count_unsummarized_messages("default") == 2

    store.update_session_summary("default", "summary one", messages[0].id)

    assert store.count_unsummarized_messages("default") == 1
    with sqlite3.connect(store.database_path) as connection:
        session = connection.execute(
            """
            SELECT summary, summary_through_message_id, updated_at
            FROM sessions WHERE id = 'default'
            """
        ).fetchone()
    assert session[0] == "summary one"
    assert session[1] == messages[0].id
    assert session[2] is not None

    store.update_session_summary("default", "summary two", messages[-1].id)
    assert store.count_unsummarized_messages("default") == 0


def test_agent_context_getter_and_upsert(store):
    assert store.get_agent_context("default", "research") == ""

    store.upsert_agent_context("default", "research", "first context", 3)
    store.upsert_agent_context("default", "research", "updated context", 7)

    assert store.get_agent_context("default", "research") == "updated context"
    with sqlite3.connect(store.database_path) as connection:
        context = connection.execute(
            """
            SELECT summary, updated_through_message_id, updated_at
            FROM agent_contexts
            WHERE session_id = 'default' AND agent_name = 'research'
            """
        ).fetchone()
    assert context[0] == "updated context"
    assert context[1] == 7
    assert context[2] is not None


def test_agent_run_start_and_finish_persistence(store):
    turn = store.start_turn("default", "request-1", {"text": "find papers"})
    completed_run_id = store.start_agent_run(
        "default",
        turn.turn_id,
        "research",
        "recommend_papers",
        {"query": "graph reconstruction"},
    )
    failed_run_id = store.start_agent_run(
        "default", turn.turn_id, "idea", "generate_ideas", {"count": 3}
    )

    store.finish_agent_run(completed_run_id, "completed", output={"papers": ["p1"]})
    store.finish_agent_run(
        failed_run_id, "failed", error={"message": "provider unavailable"}
    )

    with sqlite3.connect(store.database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM agent_runs ORDER BY started_at, id"
        ).fetchall()
    persisted = {row["id"]: row for row in rows}

    completed = persisted[completed_run_id]
    assert completed["status"] == "completed"
    assert json.loads(completed["input_json"]) == {"query": "graph reconstruction"}
    assert json.loads(completed["output_json"]) == {"papers": ["p1"]}
    assert completed["error_json"] is None
    assert completed["completed_at"] is not None

    failed = persisted[failed_run_id]
    assert failed["status"] == "failed"
    assert json.loads(failed["input_json"]) == {"count": 3}
    assert failed["output_json"] is None
    assert json.loads(failed["error_json"]) == {"message": "provider unavailable"}
    assert failed["completed_at"] is not None
