import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from services.session_schemas import StartTurnResult, StoredMessage


class SessionBusyError(RuntimeError):
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"session {session_id!r} already has a running turn")


class TurnNotFoundError(LookupError):
    def __init__(self, turn_id: str):
        self.turn_id = turn_id
        super().__init__(f"turn {turn_id!r} was not found")


class TurnStateError(RuntimeError):
    def __init__(self, turn_id: str, status: str):
        self.turn_id = turn_id
        self.status = status
        super().__init__(f"turn {turn_id!r} is {status!r}, expected 'running'")


class SessionStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    def start_turn(
        self, session_id: str, idempotency_key: str, user_content: dict
    ) -> StartTurnResult:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT id, status
                FROM conversation_turns
                WHERE session_id = ? AND idempotency_key = ?
                """,
                (session_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return StartTurnResult(
                    turn_id=existing["id"],
                    status=existing["status"],
                    replayed=True,
                )

            running = connection.execute(
                """
                SELECT id
                FROM conversation_turns
                WHERE session_id = ? AND status = 'running'
                """,
                (session_id,),
            ).fetchone()
            if running is not None:
                connection.rollback()
                raise SessionBusyError(session_id)

            turn_id = str(uuid4())
            now = self._now()
            connection.execute(
                """
                INSERT INTO conversation_turns (
                    id, session_id, idempotency_key, status, created_at
                )
                VALUES (?, ?, ?, 'running', ?)
                """,
                (turn_id, session_id, idempotency_key, now),
            )
            connection.execute(
                """
                INSERT INTO messages (
                    session_id, turn_id, role, content_json, created_at
                )
                VALUES (?, ?, 'user', ?, ?)
                """,
                (session_id, turn_id, self._to_json(user_content), now),
            )
            connection.execute(
                """
                UPDATE candidate_items
                SET status = 'expired', updated_at = ?
                WHERE status = 'active'
                  AND batch_id IN (
                      SELECT id
                      FROM candidate_batches
                      WHERE session_id = ? AND status = 'active'
                  )
                """,
                (now, session_id),
            )
            connection.execute(
                """
                UPDATE candidate_batches
                SET status = 'expired', expired_at = ?
                WHERE session_id = ? AND status = 'active'
                """,
                (now, session_id),
            )
            connection.commit()

        return StartTurnResult(turn_id=turn_id, status="running", replayed=False)

    def complete_turn(
        self, turn_id: str, assistant_content: dict, plan: dict
    ) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            turn = connection.execute(
                "SELECT session_id, status FROM conversation_turns WHERE id = ?",
                (turn_id,),
            ).fetchone()
            if turn is None:
                connection.rollback()
                raise TurnNotFoundError(turn_id)
            if turn["status"] != "running":
                connection.rollback()
                raise TurnStateError(turn_id, turn["status"])

            connection.execute(
                """
                INSERT INTO messages (
                    session_id, turn_id, role, content_json, created_at
                )
                VALUES (?, ?, 'assistant', ?, ?)
                """,
                (
                    turn["session_id"],
                    turn_id,
                    self._to_json(assistant_content),
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE conversation_turns
                SET status = 'completed', plan_json = ?, completed_at = ?
                WHERE id = ?
                """,
                (self._to_json(plan), now, turn_id),
            )
            connection.commit()

    def fail_turn(self, turn_id: str, error: Any) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            turn = connection.execute(
                "SELECT status FROM conversation_turns WHERE id = ?",
                (turn_id,),
            ).fetchone()
            if turn is None:
                connection.rollback()
                raise TurnNotFoundError(turn_id)
            if turn["status"] != "running":
                connection.rollback()
                raise TurnStateError(turn_id, turn["status"])

            connection.execute(
                """
                UPDATE conversation_turns
                SET status = 'failed', error_json = ?, completed_at = ?
                WHERE id = ?
                """,
                (self._to_json(error), now, turn_id),
            )
            connection.commit()

    def get_turn(self, session_id: str, turn_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    session_id,
                    idempotency_key,
                    status,
                    plan_json,
                    error_json,
                    created_at,
                    completed_at
                FROM conversation_turns
                WHERE session_id = ? AND id = ?
                """,
                (session_id, turn_id),
            ).fetchone()

        if row is None:
            return None
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "idempotency_key": row["idempotency_key"],
            "status": row["status"],
            "plan": self._from_json(row["plan_json"]),
            "error": self._from_json(row["error_json"]),
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }

    def get_replayed_response(self, session_id: str, turn_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT messages.content_json
                FROM messages
                JOIN conversation_turns ON conversation_turns.id = messages.turn_id
                WHERE messages.session_id = ?
                  AND messages.turn_id = ?
                  AND messages.role = 'assistant'
                  AND conversation_turns.status = 'completed'
                ORDER BY messages.id DESC
                LIMIT 1
                """,
                (session_id, turn_id),
            ).fetchone()

        if row is None:
            return None
        return self._from_json(row["content_json"])

    def list_messages(
        self, session_id: str, before_id: int | None = None, limit: int = 50
    ) -> list[StoredMessage]:
        if limit <= 0:
            return []

        where_cursor = " AND id < ?" if before_id is not None else ""
        parameters: tuple[Any, ...]
        if before_id is None:
            parameters = (session_id, limit)
        else:
            parameters = (session_id, before_id, limit)

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, session_id, turn_id, role, agent_name, content_json, created_at
                FROM messages
                WHERE session_id = ?{where_cursor}
                ORDER BY id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()

        return [self._stored_message(row) for row in reversed(rows)]

    def get_session(self, session_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, title, summary, summary_through_message_id, status,
                       created_at, updated_at
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()

        return None if row is None else dict(row)

    def list_unsummarized_messages(self, session_id: str) -> list[StoredMessage]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT messages.id, messages.session_id, messages.turn_id,
                       messages.role, messages.agent_name,
                       messages.content_json, messages.created_at
                FROM messages
                JOIN sessions ON sessions.id = messages.session_id
                WHERE messages.session_id = ?
                  AND (
                      sessions.summary_through_message_id IS NULL
                      OR messages.id > sessions.summary_through_message_id
                  )
                ORDER BY messages.id
                """,
                (session_id,),
            ).fetchall()

        return [self._stored_message(row) for row in rows]

    def list_recent_turn_messages(
        self, session_id: str, turn_limit: int = 6
    ) -> list[StoredMessage]:
        if turn_limit <= 0:
            return []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    messages.id,
                    messages.session_id,
                    messages.turn_id,
                    messages.role,
                    messages.agent_name,
                    messages.content_json,
                    messages.created_at
                FROM messages
                WHERE messages.session_id = ?
                  AND messages.turn_id IN (
                      SELECT id
                      FROM conversation_turns
                      WHERE session_id = ? AND status = 'completed'
                      ORDER BY completed_at DESC, rowid DESC
                      LIMIT ?
                  )
                ORDER BY messages.id
                """,
                (session_id, session_id, turn_limit),
            ).fetchall()

        return [self._stored_message(row) for row in rows]

    def count_unsummarized_messages(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS message_count
                FROM messages
                JOIN sessions ON sessions.id = messages.session_id
                WHERE messages.session_id = ?
                  AND (
                      sessions.summary_through_message_id IS NULL
                      OR messages.id > sessions.summary_through_message_id
                  )
                """,
                (session_id,),
            ).fetchone()
        return int(row["message_count"])

    def update_session_summary(
        self, session_id: str, summary: str, through_message_id: int
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET summary = ?, summary_through_message_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (summary, through_message_id, self._now(), session_id),
            )

    def get_agent_context(self, session_id: str, agent_name: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT summary
                FROM agent_contexts
                WHERE session_id = ? AND agent_name = ?
                """,
                (session_id, agent_name),
            ).fetchone()
        return "" if row is None else row["summary"]

    def upsert_agent_context(
        self,
        session_id: str,
        agent_name: str,
        summary: str,
        through_message_id: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_contexts (
                    session_id,
                    agent_name,
                    summary,
                    updated_through_message_id,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id, agent_name) DO UPDATE SET
                    summary = excluded.summary,
                    updated_through_message_id = excluded.updated_through_message_id,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    agent_name,
                    summary,
                    through_message_id,
                    self._now(),
                ),
            )

    def start_agent_run(
        self,
        session_id: str,
        turn_id: str,
        agent_name: str,
        action: str,
        input_data: Any,
    ) -> str:
        run_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    id,
                    session_id,
                    turn_id,
                    agent_name,
                    action,
                    status,
                    input_json,
                    started_at
                )
                VALUES (?, ?, ?, ?, ?, 'running', ?, ?)
                """,
                (
                    run_id,
                    session_id,
                    turn_id,
                    agent_name,
                    action,
                    self._to_json(input_data),
                    self._now(),
                ),
            )
        return run_id

    def finish_agent_run(
        self,
        run_id: str,
        status: str,
        output: Any = None,
        error: Any = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE agent_runs
                SET status = ?, output_json = ?, error_json = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    None if output is None else self._to_json(output),
                    None if error is None else self._to_json(error),
                    self._now(),
                    run_id,
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _stored_message(self, row: sqlite3.Row) -> StoredMessage:
        return StoredMessage(
            id=row["id"],
            session_id=row["session_id"],
            turn_id=row["turn_id"],
            role=row["role"],
            agent_name=row["agent_name"],
            content=self._from_json(row["content_json"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _to_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _from_json(value: str | None) -> Any:
        return None if value is None else json.loads(value)
