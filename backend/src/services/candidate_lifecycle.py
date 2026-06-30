import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from services.schemas import JudgeResult, PaperMetadata
from services.session_schemas import (
    CandidateAcceptResponse,
    CandidateBatch,
    SavedPaper,
    SessionCandidate,
)

SAVED_PAPER_STATUSES = ("accepted", "uploaded", "chunked", "embedded")


class CandidateExpiredError(RuntimeError):
    def __init__(self, candidate_id: str):
        self.candidate_id = candidate_id
        super().__init__(f"candidate {candidate_id!r} has expired")


def paper_key(paper: dict) -> str:
    raw_doi = paper.get("doi") or (paper.get("source_ids") or {}).get("doi")
    if raw_doi:
        normalized = raw_doi.strip().lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
                break
        return f"doi:{normalized}"
    return f"paper:{paper['paper_id']}"


class CandidateLifecycleService:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    def suppression_keys(self, session_id: str) -> set[str]:
        keys = set()
        with self._connect() as connection:
            saved_rows = connection.execute(
                """
                SELECT doi, paper_id
                FROM papers
                WHERE status IN ('accepted', 'uploaded', 'chunked', 'embedded')
                """
            ).fetchall()
            for row in saved_rows:
                keys.add(
                    paper_key(
                        {
                            "paper_id": row["paper_id"],
                            "doi": row["doi"],
                            "source_ids": {"doi": row["doi"]},
                        }
                    )
                )

            batch = connection.execute(
                """
                SELECT id
                FROM candidate_batches
                WHERE session_id = ? AND status = 'expired'
                ORDER BY COALESCE(expired_at, created_at) DESC, id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if batch is not None:
                item_rows = connection.execute(
                    """
                    SELECT paper_key
                    FROM candidate_items
                    WHERE batch_id = ?
                    """,
                    (batch["id"],),
                ).fetchall()
                keys.update(row["paper_key"] for row in item_rows)

        return keys

    def filter_fresh(
        self, session_id: str, ranked_candidates: list[dict], top_k: int
    ) -> list[dict]:
        suppressed = self.suppression_keys(session_id)
        fresh: list[dict] = []
        for candidate in ranked_candidates:
            key = paper_key(self._paper_payload(candidate))
            if key in suppressed:
                continue
            fresh.append(candidate)
            if len(fresh) >= top_k:
                break
        return fresh

    def create_batch(
        self, session_id: str, turn_id: str, query: str, candidates: list[dict]
    ) -> CandidateBatch:
        batch_id = str(uuid4())
        now = self._now()
        session_candidates: list[SessionCandidate] = []

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO candidate_batches (
                    id, session_id, turn_id, query, status, created_at
                )
                VALUES (?, ?, ?, ?, 'active', ?)
                """,
                (batch_id, session_id, turn_id, query, now),
            )

            for candidate in candidates:
                candidate_id = str(uuid4())
                paper_payload = self._paper_payload(candidate)
                judgement_payload = self._judgement_payload(candidate)
                key = paper_key(paper_payload)
                connection.execute(
                    """
                    INSERT INTO candidate_items (
                        id,
                        batch_id,
                        paper_key,
                        paper_snapshot_json,
                        judgement_json,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        candidate_id,
                        batch_id,
                        key,
                        self._to_json(paper_payload),
                        None if judgement_payload is None else self._to_json(judgement_payload),
                        now,
                        now,
                    ),
                )
                session_candidates.append(
                    SessionCandidate(
                        id=candidate_id,
                        batch_id=batch_id,
                        paper_key=key,
                        paper_snapshot=PaperMetadata(**paper_payload),
                        judgement=None
                        if judgement_payload is None
                        else JudgeResult(**judgement_payload),
                        status="active",
                    )
                )

        return CandidateBatch(
            id=batch_id,
            session_id=session_id,
            turn_id=turn_id,
            query=query,
            status="active",
            candidates=session_candidates,
        )

    def list_active(self, session_id: str) -> list[SessionCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    items.id,
                    items.batch_id,
                    items.paper_key,
                    items.paper_snapshot_json,
                    items.judgement_json,
                    items.status
                FROM candidate_items AS items
                JOIN candidate_batches AS batches ON batches.id = items.batch_id
                WHERE batches.session_id = ?
                  AND batches.status = 'active'
                  AND items.status = 'active'
                ORDER BY items.created_at ASC, items.id ASC
                """,
                (session_id,),
            ).fetchall()

        return [self._session_candidate_from_row(row) for row in rows]

    def accept(self, session_id: str, candidate_id: str) -> CandidateAcceptResponse:
        now = self._now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT
                    items.id,
                    items.paper_snapshot_json,
                    items.judgement_json,
                    items.status,
                    items.accepted_paper_id,
                    batches.session_id
                FROM candidate_items AS items
                JOIN candidate_batches AS batches ON batches.id = items.batch_id
                WHERE items.id = ? AND batches.session_id = ?
                """,
                (candidate_id, session_id),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise ValueError(f"candidate not found: {candidate_id}")
            if row["status"] == "accepted":
                connection.commit()
                return CandidateAcceptResponse(
                    candidate_id=candidate_id,
                    paper_id=row["accepted_paper_id"],
                )
            if row["status"] == "expired":
                connection.rollback()
                raise CandidateExpiredError(candidate_id)

            paper = PaperMetadata(**self._from_json(row["paper_snapshot_json"]))
            judgement_payload = self._from_json(row["judgement_json"])
            judgement = (
                None if judgement_payload is None else JudgeResult(**judgement_payload)
            )
            existing = connection.execute(
                """
                SELECT status, pdf_path, created_at
                FROM papers
                WHERE paper_id = ?
                """,
                (paper.paper_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing is not None else now
            pdf_path = existing["pdf_path"] if existing is not None else None
            next_status = "accepted"
            if existing is not None and existing["status"] in {
                "uploaded",
                "chunked",
                "embedded",
            }:
                next_status = existing["status"]

            connection.execute(
                """
                INSERT INTO papers (
                    paper_id,
                    title,
                    doi,
                    source,
                    abstract,
                    authors_json,
                    metadata_json,
                    status,
                    pdf_path,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(paper_id) DO UPDATE SET
                    title = excluded.title,
                    doi = excluded.doi,
                    source = excluded.source,
                    abstract = excluded.abstract,
                    authors_json = excluded.authors_json,
                    metadata_json = excluded.metadata_json,
                    status = excluded.status,
                    pdf_path = excluded.pdf_path,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    paper.paper_id,
                    paper.title,
                    self._normalize_doi(paper.doi or paper.source_ids.doi),
                    paper.source,
                    paper.abstract,
                    self._to_json(paper.authors),
                    self._to_json(paper.model_dump()),
                    next_status,
                    pdf_path,
                    created_at,
                    now,
                ),
            )
            if judgement is not None:
                scores = {
                    "llm_relevance_score": judgement.llm_relevance_score,
                    "embedding_relevance_score": judgement.embedding_relevance_score,
                    "quality_score": judgement.quality_score,
                    "novelty_score": judgement.novelty_score,
                    "final_score": judgement.final_score,
                }
                connection.execute(
                    """
                    INSERT INTO paper_judgements (
                        paper_id,
                        decision,
                        reason,
                        scores_json,
                        tags_json,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        paper.paper_id,
                        judgement.decision,
                        judgement.reason,
                        self._to_json(scores),
                        self._to_json(judgement.tags),
                        now,
                    ),
                )
            connection.execute(
                """
                UPDATE candidate_items
                SET status = 'accepted', accepted_paper_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (paper.paper_id, now, candidate_id),
            )
            connection.commit()
            return CandidateAcceptResponse(
                candidate_id=candidate_id,
                paper_id=paper.paper_id,
            )

    def get_item_status(self, candidate_key: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT status
                FROM candidate_items
                WHERE paper_key = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (candidate_key,),
            ).fetchone()
        return None if row is None else row["status"]

    def get_saved_paper(self, paper_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT paper_id, title, doi, source, authors_json, status, pdf_path
                FROM papers
                WHERE paper_id = ?
                  AND status IN ('accepted', 'uploaded', 'chunked', 'embedded')
                """,
                (paper_id,),
            ).fetchone()
        if row is None:
            return None
        return SavedPaper(
            paper_id=row["paper_id"],
            title=row["title"],
            doi=row["doi"],
            source=row["source"],
            authors=self._from_json(row["authors_json"]),
            status=row["status"],
            pdf_path=row["pdf_path"],
        ).model_dump()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _session_candidate_from_row(self, row: sqlite3.Row) -> SessionCandidate:
        judgement_payload = self._from_json(row["judgement_json"])
        return SessionCandidate(
            id=row["id"],
            batch_id=row["batch_id"],
            paper_key=row["paper_key"],
            paper_snapshot=PaperMetadata(**self._from_json(row["paper_snapshot_json"])),
            judgement=None
            if judgement_payload is None
            else JudgeResult(**judgement_payload),
            status=row["status"],
        )

    @staticmethod
    def _paper_payload(candidate: dict) -> dict:
        paper = candidate.get("paper")
        if isinstance(paper, dict) and "paper_id" in paper:
            return paper
        return candidate

    @staticmethod
    def _judgement_payload(candidate: dict) -> dict | None:
        judgement = candidate.get("judgement")
        return judgement if isinstance(judgement, dict) else None

    @staticmethod
    def _normalize_doi(doi: str | None) -> str | None:
        if doi is None:
            return None
        normalized = doi.strip().lower()
        if not normalized:
            return None
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
                break
        return normalized or None

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _to_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _from_json(value: str | None) -> Any:
        return None if value is None else json.loads(value)
