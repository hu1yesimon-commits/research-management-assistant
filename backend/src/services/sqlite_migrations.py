import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path


MIGRATIONS: Sequence[tuple[int, str]] = (
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            summary TEXT NOT NULL DEFAULT '',
            summary_through_message_id INTEGER,
            status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS conversation_turns (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
            plan_json TEXT,
            error_json TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            UNIQUE(session_id, idempotency_key)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_running_turn_per_session
            ON conversation_turns(session_id) WHERE status = 'running';
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            turn_id TEXT NOT NULL REFERENCES conversation_turns(id),
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'agent', 'system')),
            agent_name TEXT,
            content_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS messages_session_id_id
            ON messages(session_id, id);
        CREATE TABLE IF NOT EXISTS candidate_batches (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            turn_id TEXT NOT NULL REFERENCES conversation_turns(id),
            query TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'expired')),
            created_at TEXT NOT NULL,
            expired_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_batch_per_session
            ON candidate_batches(session_id) WHERE status = 'active';
        CREATE TABLE IF NOT EXISTS candidate_items (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL REFERENCES candidate_batches(id),
            paper_key TEXT NOT NULL,
            paper_snapshot_json TEXT NOT NULL,
            judgement_json TEXT,
            status TEXT NOT NULL CHECK (status IN ('active', 'accepted', 'expired')),
            accepted_paper_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(batch_id, paper_key)
        );
        CREATE TABLE IF NOT EXISTS agent_contexts (
            session_id TEXT NOT NULL REFERENCES sessions(id),
            agent_name TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            updated_through_message_id INTEGER,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(session_id, agent_name)
        );
        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            turn_id TEXT NOT NULL REFERENCES conversation_turns(id),
            agent_name TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'skipped')),
            input_json TEXT NOT NULL,
            output_json TEXT,
            error_json TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT
        );
        """,
    ),
)


def apply_migrations(database_path: str | Path) -> None:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path, timeout=5.0) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )

        applied_versions = {
            row["version"]
            for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
        }

        for version, migration_sql in MIGRATIONS:
            if version in applied_versions:
                continue

            applied_at = _utc_now()
            connection.execute("BEGIN IMMEDIATE")
            try:
                for statement in _split_sql_statements(migration_sql):
                    connection.execute(statement)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO schema_migrations (version, applied_at)
                    VALUES (?, ?)
                    """,
                    (version, applied_at),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        now = _utc_now()
        connection.execute(
            """
            INSERT OR IGNORE INTO sessions (id, title, summary, summary_through_message_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("default", "Default Session", "", None, "active", now, now),
        )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _split_sql_statements(sql: str) -> list[str]:
    return [statement.strip() for statement in sql.split(";") if statement.strip()]
