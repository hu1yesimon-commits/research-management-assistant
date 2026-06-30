import sqlite3

from services.memory_store import MemoryStore
from services import sqlite_migrations


def test_initialize_applies_v3_migrations_and_creates_default_session(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))

    store.initialize()

    with sqlite3.connect(store.database_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        index_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        default_session = connection.execute(
            "SELECT id, status FROM sessions WHERE id = 'default'"
        ).fetchone()
        migration_versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert {
        "schema_migrations",
        "sessions",
        "conversation_turns",
        "messages",
        "candidate_batches",
        "candidate_items",
        "agent_contexts",
        "agent_runs",
    } <= table_names
    assert {
        "one_running_turn_per_session",
        "messages_session_id_id",
        "one_active_batch_per_session",
    } <= index_names
    assert default_session == ("default", "active")
    assert migration_versions == [(1,)]


def test_initialize_is_idempotent_for_default_session_and_migration_records(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))

    store.initialize()
    store.initialize()

    with sqlite3.connect(store.database_path) as connection:
        default_session_count = connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE id = 'default'"
        ).fetchone()[0]
        migration_count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 1"
        ).fetchone()[0]

    assert default_session_count == 1
    assert migration_count == 1


def test_apply_migrations_rolls_back_schema_changes_when_a_migration_fails(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    original_migrations = sqlite_migrations.MIGRATIONS
    sqlite_migrations.MIGRATIONS = (
        (
            1,
            """
            CREATE TABLE partial_table (
                id INTEGER PRIMARY KEY
            );
            INSERT INTO missing_table (id) VALUES (1);
            """,
        ),
    )

    try:
        try:
            sqlite_migrations.apply_migrations(db_path)
        except sqlite3.OperationalError:
            pass
        else:
            raise AssertionError("expected migration failure")
    finally:
        sqlite_migrations.MIGRATIONS = original_migrations

    with sqlite3.connect(db_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        migration_count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 1"
        ).fetchone()[0]

    assert "partial_table" not in table_names
    assert migration_count == 0
