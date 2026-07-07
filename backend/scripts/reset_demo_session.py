#!/usr/bin/env python3
"""Reset persistent Agent Team demo session state without deleting saved papers."""

from __future__ import annotations

import argparse
import sqlite3
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path

from services.memory_store import MemoryStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-path",
        default="backend/data/research_memory.sqlite3",
        help="SQLite database path to reset.",
    )
    parser.add_argument(
        "--session-id",
        default="default",
        help="Session id to reset. Defaults to the persistent demo session.",
    )
    return parser


def reset_demo_session(database_path: str | Path, session_id: str = "default") -> dict[str, int]:
    database_path = Path(database_path)
    MemoryStore(str(database_path)).initialize()

    batch_id_query = (
        "SELECT id FROM candidate_batches WHERE session_id = ?"
    )
    counts: OrderedDict[str, int] = OrderedDict()

    with sqlite3.connect(database_path, timeout=5.0) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")

        counts["agent_runs"] = connection.execute(
            "DELETE FROM agent_runs WHERE session_id = ?",
            (session_id,),
        ).rowcount
        counts["agent_contexts"] = connection.execute(
            "DELETE FROM agent_contexts WHERE session_id = ?",
            (session_id,),
        ).rowcount
        counts["candidate_items"] = connection.execute(
            f"DELETE FROM candidate_items WHERE batch_id IN ({batch_id_query})",
            (session_id,),
        ).rowcount
        counts["candidate_batches"] = connection.execute(
            "DELETE FROM candidate_batches WHERE session_id = ?",
            (session_id,),
        ).rowcount
        counts["messages"] = connection.execute(
            "DELETE FROM messages WHERE session_id = ?",
            (session_id,),
        ).rowcount
        counts["conversation_turns"] = connection.execute(
            "DELETE FROM conversation_turns WHERE session_id = ?",
            (session_id,),
        ).rowcount
        connection.execute(
            """
            UPDATE sessions
            SET summary = '', summary_through_message_id = NULL, updated_at = ?
            WHERE id = ?
            """,
            (_utc_now(), session_id),
        )
        connection.commit()

    return dict(counts)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def main() -> None:
    args = build_parser().parse_args()
    counts = reset_demo_session(args.database_path, session_id=args.session_id)

    print(f"RESET_DATABASE_PATH={Path(args.database_path)}")
    print(f"RESET_SESSION_ID={args.session_id}")
    for table_name, deleted_rows in counts.items():
        print(f"DELETED_{table_name.upper()}={deleted_rows}")
    print("DEMO_SESSION_RESET_OK=true")


if __name__ == "__main__":
    main()
