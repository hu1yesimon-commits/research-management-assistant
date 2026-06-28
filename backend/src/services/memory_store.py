import json
import sqlite3
from datetime import datetime, UTC
from pathlib import Path

from services.schemas import JudgeResult, PaperMetadata

"""
2026-06-07 更新：
 MemoryStore 现在有 papers、paper_judgements、experiment_logs 三张表，
 也有日志增查、候选论文保存查询、评审结果保存、DOI 查询与归一化、paper 状态更新等方法。

 当前 MemoryStore 够 Phase 2A，但还不是最终完整 memory layer。

暂时缺的能力包括：

    没有 conversations 表。
    没有 knowledge_chunks 表。
    没有按 paper_id 查询单篇 paper 的公开方法。
    没有 rejected / accepted 专门方法，只能通过 update_paper_status() 改。
    没有复杂迁移机制，SQLite schema 现在还是 MVP 固定建表。
    这些不是当前阻塞，因为 Phase 2A 只需要 logs、candidates、known DOI 和状态更新。


""" 

class MemoryStore:
    def __init__(self, database_path: str):
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        # 对数据库文件所在目录进行确保，避免因目录不存在导致的错误
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        # 初始化数据库表结构，将已收录的论文信息和实验日志存储在本地 SQLite 数据库中
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS papers (
                    paper_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    doi TEXT,
                    source TEXT NOT NULL,
                    abstract TEXT,
                    authors_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    pdf_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS paper_judgements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT,
                    scores_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
                );

                CREATE TABLE IF NOT EXISTS experiment_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS experiment_log_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT NOT NULL,
                    model TEXT NOT NULL,
                    dataset TEXT NOT NULL,
                    metric_problem TEXT NOT NULL,
                    tried_methods_json TEXT NOT NULL,
                    observation TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    chunk_hash TEXT NOT NULL,
                    vector_ref TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
                );

                CREATE TABLE IF NOT EXISTS memory_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    source_log_ids_json TEXT NOT NULL,
                    evidence_count INTEGER NOT NULL,
                    score REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    UNIQUE(candidate_type, category, subject, predicate, object)
                );

                CREATE TABLE IF NOT EXISTS semantic_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    support_count INTEGER NOT NULL,
                    supporting_log_ids_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_confirmed_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(category, subject, predicate, object)
                );
                """
            )

    def add_experiment_log(self, content: str, tags: list[str] | None = None) -> int:
        now = self._now()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO experiment_logs (content, tags_json, created_at)
                VALUES (?, ?, ?)
                """,
                (content, self._to_json(tags or []), now),
            )
            return int(cursor.lastrowid)

    def list_experiment_logs(self, limit: int = 50) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, content, tags_json, created_at
                FROM experiment_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "id": row["id"],
                "content": row["content"],
                "tags": self._from_json(row["tags_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def add_experiment_log_entry(self, entry: dict) -> int:
        now = self._now()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO experiment_log_entries (
                    task,
                    model,
                    dataset,
                    metric_problem,
                    tried_methods_json,
                    observation,
                    goal,
                    tags_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["task"],
                    entry["model"],
                    entry["dataset"],
                    entry["metric_problem"],
                    self._to_json(entry.get("tried_methods", [])),
                    entry["observation"],
                    entry["goal"],
                    self._to_json(entry.get("tags", [])),
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def list_experiment_log_entries(self, limit: int = 50) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    task,
                    model,
                    dataset,
                    metric_problem,
                    tried_methods_json,
                    observation,
                    goal,
                    tags_json,
                    created_at
                FROM experiment_log_entries
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "id": row["id"],
                "task": row["task"],
                "model": row["model"],
                "dataset": row["dataset"],
                "metric_problem": row["metric_problem"],
                "tried_methods": self._from_json(row["tried_methods_json"]),
                "observation": row["observation"],
                "goal": row["goal"],
                "tags": self._from_json(row["tags_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def build_memory_context(self, limit: int = 3) -> str:
        semantic_memories = self.list_semantic_memory(status="confirmed")
        entries = self.list_experiment_log_entries(limit=3)
        lines = ["Confirmed semantic memory:"]

        for memory in semantic_memories:
            lines.append(
                "- "
                f"[{memory['category']}/{memory['predicate']}] "
                f"{memory['subject']} {memory['predicate']} {memory['object']}: "
                f"{memory['summary']}"
            )

        lines.append("Recent episodic memory:")
        for entry in entries:
            tried_methods = ", ".join(entry.get("tried_methods", []))
            tags = ", ".join(entry.get("tags", []))
            lines.append(
                "- "
                f"task={entry['task']}; "
                f"model={entry['model']}; "
                f"dataset={entry['dataset']}; "
                f"metric_problem={entry['metric_problem']}; "
                f"tried_methods={tried_methods}; "
                f"observation={entry['observation']}; "
                f"goal={entry['goal']}; "
                f"tags={tags}"
            )

        return "\n".join(lines)

    def upsert_memory_candidate(self, candidate: dict) -> int:
        now = self._now()
        source_log_ids = candidate.get("source_log_ids", [])
        evidence_count = len(source_log_ids) if source_log_ids else candidate.get("evidence_count", 0)

        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT id, created_at
                FROM memory_candidates
                WHERE candidate_type = ?
                  AND category = ?
                  AND subject = ?
                  AND predicate = ?
                  AND object = ?
                """,
                (
                    candidate["candidate_type"],
                    candidate["category"],
                    candidate["subject"],
                    candidate["predicate"],
                    candidate["object"],
                ),
            ).fetchone()

            if existing is not None:
                connection.execute(
                    """
                    UPDATE memory_candidates
                    SET summary = ?,
                        source_log_ids_json = ?,
                        evidence_count = ?,
                        score = ?,
                        status = ?,
                        reviewed_at = ?
                    WHERE id = ?
                    """,
                    (
                        candidate["summary"],
                        self._to_json(source_log_ids),
                        evidence_count,
                        candidate["score"],
                        candidate.get("status", "pending"),
                        candidate.get("reviewed_at"),
                        existing["id"],
                    ),
                )
                return int(existing["id"])

            cursor = connection.execute(
                """
                INSERT INTO memory_candidates (
                    candidate_type,
                    category,
                    subject,
                    predicate,
                    object,
                    summary,
                    source_log_ids_json,
                    evidence_count,
                    score,
                    status,
                    created_at,
                    reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate["candidate_type"],
                    candidate["category"],
                    candidate["subject"],
                    candidate["predicate"],
                    candidate["object"],
                    candidate["summary"],
                    self._to_json(source_log_ids),
                    evidence_count,
                    candidate["score"],
                    candidate.get("status", "pending"),
                    now,
                    candidate.get("reviewed_at"),
                ),
            )
            return int(cursor.lastrowid)

    def list_memory_candidates(
        self,
        status: str = "pending",
        candidate_type: str | None = None,
        category: str | None = None,
    ) -> list[dict]:
        query = """
            SELECT
                id,
                candidate_type,
                category,
                subject,
                predicate,
                object,
                summary,
                source_log_ids_json,
                evidence_count,
                score,
                status,
                created_at,
                reviewed_at
            FROM memory_candidates
            WHERE status = ?
        """
        params: list[object] = [status]

        if candidate_type is not None:
            query += " AND candidate_type = ?"
            params.append(candidate_type)
        if category is not None:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY evidence_count DESC, score DESC, id ASC"

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()

        return [self._memory_candidate_from_row(row) for row in rows]

    def get_memory_candidate(self, candidate_id: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    candidate_type,
                    category,
                    subject,
                    predicate,
                    object,
                    summary,
                    source_log_ids_json,
                    evidence_count,
                    score,
                    status,
                    created_at,
                    reviewed_at
                FROM memory_candidates
                WHERE id = ?
                """,
                (candidate_id,),
            ).fetchone()

        if row is None:
            return None
        return self._memory_candidate_from_row(row)

    def update_memory_candidate_status(self, candidate_id: int, status: str) -> dict:
        reviewed_at = self._now() if status in {"accepted", "rejected", "expired"} else None
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE memory_candidates
                SET status = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (status, reviewed_at, candidate_id),
            )

        candidate = self.get_memory_candidate(candidate_id)
        if candidate is None:
            raise ValueError(f"memory candidate not found: {candidate_id}")
        return candidate

    def upsert_semantic_memory_from_candidate(self, candidate: dict) -> int:
        now = self._now()
        source_log_ids = candidate.get("source_log_ids", [])

        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT id, created_at
                FROM semantic_memory
                WHERE category = ?
                  AND subject = ?
                  AND predicate = ?
                  AND object = ?
                """,
                (
                    candidate["category"],
                    candidate["subject"],
                    candidate["predicate"],
                    candidate["object"],
                ),
            ).fetchone()

            if existing is not None:
                connection.execute(
                    """
                    UPDATE semantic_memory
                    SET summary = ?,
                        confidence = ?,
                        support_count = ?,
                        supporting_log_ids_json = ?,
                        status = 'confirmed',
                        last_confirmed_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        candidate["summary"],
                        candidate["score"],
                        candidate["evidence_count"],
                        self._to_json(source_log_ids),
                        now,
                        now,
                        existing["id"],
                    ),
                )
                return int(existing["id"])

            cursor = connection.execute(
                """
                INSERT INTO semantic_memory (
                    category,
                    subject,
                    predicate,
                    object,
                    summary,
                    confidence,
                    support_count,
                    supporting_log_ids_json,
                    status,
                    last_confirmed_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate["category"],
                    candidate["subject"],
                    candidate["predicate"],
                    candidate["object"],
                    candidate["summary"],
                    candidate["score"],
                    candidate["evidence_count"],
                    self._to_json(source_log_ids),
                    "confirmed",
                    now,
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def list_semantic_memory(
        self,
        status: str = "confirmed",
        category: str | None = None,
        predicate: str | None = None,
    ) -> list[dict]:
        query = """
            SELECT
                id,
                category,
                subject,
                predicate,
                object,
                summary,
                confidence,
                support_count,
                supporting_log_ids_json,
                status,
                last_confirmed_at,
                created_at,
                updated_at
            FROM semantic_memory
            WHERE status = ?
        """
        params: list[object] = [status]

        if category is not None:
            query += " AND category = ?"
            params.append(category)
        if predicate is not None:
            query += " AND predicate = ?"
            params.append(predicate)

        query += " ORDER BY support_count DESC, updated_at DESC, id ASC"

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()

        return [self._semantic_memory_from_row(row) for row in rows]

    def get_semantic_memory(self, memory_id: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    category,
                    subject,
                    predicate,
                    object,
                    summary,
                    confidence,
                    support_count,
                    supporting_log_ids_json,
                    status,
                    last_confirmed_at,
                    created_at,
                    updated_at
                FROM semantic_memory
                WHERE id = ?
                """,
                (memory_id,),
            ).fetchone()

        if row is None:
            return None
        return self._semantic_memory_from_row(row)

    def archive_semantic_memory(self, memory_id: int) -> dict:
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE semantic_memory
                SET status = 'archived', updated_at = ?
                WHERE id = ?
                """,
                (now, memory_id),
            )

        memory = self.get_semantic_memory(memory_id)
        if memory is None:
            raise ValueError(f"semantic memory not found: {memory_id}")
        return memory

    def save_candidate_paper(
        self,
        paper: PaperMetadata,
        judgement: JudgeResult | None = None,
    ) -> None:
        existing = self._get_existing_paper(paper.paper_id)
        now = self._now()
        created_at = existing["created_at"] if existing else now
        status = existing["status"] if existing else "candidate"
        pdf_path = existing["pdf_path"] if existing else None

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO papers (
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
                """,
                (
                    paper.paper_id,
                    paper.title,
                    self._normalize_doi(paper.doi or paper.source_ids.doi),
                    paper.source,
                    paper.abstract,
                    self._to_json(paper.authors),
                    self._to_json(paper.model_dump()),
                    status,
                    pdf_path,
                    created_at,
                    now,
                ),
            )

        if judgement is not None:
            self.save_judge_result(paper.paper_id, judgement)

    def save_judge_result(self, paper_id: str, judgement: JudgeResult) -> int:
        scores = {
            "llm_relevance_score": judgement.llm_relevance_score,
            "embedding_relevance_score": judgement.embedding_relevance_score,
            "quality_score": judgement.quality_score,
            "novelty_score": judgement.novelty_score,
            "final_score": judgement.final_score,
        }

        with self._connect() as connection:
            cursor = connection.execute(
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
                    paper_id,
                    judgement.decision,
                    judgement.reason,
                    self._to_json(scores),
                    self._to_json(judgement.tags),
                    self._now(),
                ),
            )
            return int(cursor.lastrowid)

    def list_candidate_papers(self, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    p.paper_id,
                    p.title,
                    p.doi,
                    p.source,
                    p.abstract,
                    p.authors_json,
                    p.metadata_json,
                    p.status,
                    p.pdf_path,
                    p.created_at,
                    p.updated_at,
                    j.decision,
                    j.reason,
                    j.scores_json,
                    j.tags_json,
                    j.created_at AS judgement_created_at
                FROM papers AS p
                LEFT JOIN (
                    SELECT j1.*
                    FROM paper_judgements AS j1
                    INNER JOIN (
                        SELECT paper_id, MAX(id) AS max_id
                        FROM paper_judgements
                        GROUP BY paper_id
                    ) AS latest
                    ON latest.paper_id = j1.paper_id AND latest.max_id = j1.id
                ) AS j
                ON j.paper_id = p.paper_id
                ORDER BY p.updated_at DESC, p.paper_id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        candidates = []
        for row in rows:
            item = {
                "paper_id": row["paper_id"],
                "title": row["title"],
                "doi": row["doi"],
                "source": row["source"],
                "abstract": row["abstract"],
                "authors": self._from_json(row["authors_json"]),
                "metadata": self._from_json(row["metadata_json"]),
                "status": row["status"],
                "pdf_path": row["pdf_path"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            if row["decision"] is not None:
                item["judgement"] = {
                    "decision": row["decision"],
                    "reason": row["reason"],
                    "scores": self._from_json(row["scores_json"]),
                    "tags": self._from_json(row["tags_json"]),
                    "created_at": row["judgement_created_at"],
                }
            candidates.append(item)

        return candidates

    def count_candidate_papers(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS paper_count
                FROM papers
                """
            ).fetchone()

        return int(row["paper_count"])

    def get_paper(self, paper_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
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
                FROM papers
                WHERE paper_id = ?
                """,
                (paper_id,),
            ).fetchone()

        if row is None:
            return None

        return {
            "paper_id": row["paper_id"],
            "title": row["title"],
            "doi": row["doi"],
            "source": row["source"],
            "abstract": row["abstract"],
            "authors": self._from_json(row["authors_json"]),
            "metadata": self._from_json(row["metadata_json"]),
            "status": row["status"],
            "pdf_path": row["pdf_path"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def update_paper_status(self, paper_id: str, status: str, pdf_path: str | None = None) -> None:
        existing = self._get_existing_paper(paper_id)
        if existing is None:
            raise ValueError(f"paper not found: {paper_id}")

        next_pdf_path = pdf_path if pdf_path is not None else existing["pdf_path"]

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE papers
                SET status = ?, pdf_path = ?, updated_at = ?
                WHERE paper_id = ?
                """,
                (status, next_pdf_path, self._now(), paper_id),
            )

    def list_known_dois(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT doi
                FROM papers
                WHERE status IN ('uploaded', 'chunked', 'embedded')
                  AND doi IS NOT NULL
                  AND doi != ''
                ORDER BY doi ASC
                """
            ).fetchall()

        return [row["doi"] for row in rows]

    def insert_knowledge_chunks(self, paper_id: str, chunks: list[dict]) -> None:
        now = self._now()
        rows = [
            (
                paper_id,
                chunk["chunk_index"],
                chunk["text"],
                chunk["chunk_hash"],
                chunk.get("vector_ref"),
                now,
            )
            for chunk in chunks
        ]

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO knowledge_chunks (
                    paper_id,
                    chunk_index,
                    text,
                    chunk_hash,
                    vector_ref,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def list_knowledge_chunks(self, paper_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    paper_id,
                    chunk_index,
                    text,
                    chunk_hash,
                    vector_ref,
                    created_at
                FROM knowledge_chunks
                WHERE paper_id = ?
                ORDER BY chunk_index ASC, id ASC
                """,
                (paper_id,),
            ).fetchall()

        return [
            {
                "id": row["id"],
                "paper_id": row["paper_id"],
                "chunk_index": row["chunk_index"],
                "text": row["text"],
                "chunk_hash": row["chunk_hash"],
                "vector_ref": row["vector_ref"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_knowledge_chunk(self, paper_id: str, chunk_index: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    paper_id,
                    chunk_index,
                    text,
                    chunk_hash,
                    vector_ref,
                    created_at
                FROM knowledge_chunks
                WHERE paper_id = ? AND chunk_index = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (paper_id, chunk_index),
            ).fetchone()

        if row is None:
            return None

        return {
            "id": row["id"],
            "paper_id": row["paper_id"],
            "chunk_index": row["chunk_index"],
            "text": row["text"],
            "chunk_hash": row["chunk_hash"],
            "vector_ref": row["vector_ref"],
            "created_at": row["created_at"],
        }

    def update_knowledge_chunk_vector_refs(self, paper_id: str, updates: list[dict]) -> None:
        rows = [
            (update["vector_ref"], paper_id, update["chunk_index"])
            for update in updates
        ]
        if not rows:
            return

        with self._connect() as connection:
            connection.executemany(
                """
                UPDATE knowledge_chunks
                SET vector_ref = ?
                WHERE paper_id = ? AND chunk_index = ?
                """,
                rows,
            )

    def clear_knowledge_chunk_vector_refs(self, paper_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE knowledge_chunks
                SET vector_ref = NULL
                WHERE paper_id = ?
                """,
                (paper_id,),
            )

    def has_complete_knowledge_chunk_vector_refs(self, paper_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS chunk_count,
                    SUM(
                        CASE
                            WHEN vector_ref IS NOT NULL AND TRIM(vector_ref) != '' THEN 1
                            ELSE 0
                        END
                    ) AS complete_count
                FROM knowledge_chunks
                WHERE paper_id = ?
                """,
                (paper_id,),
            ).fetchone()

        if row is None or row["chunk_count"] == 0:
            return False

        return row["chunk_count"] == row["complete_count"]

    def delete_knowledge_chunks_by_paper(self, paper_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM knowledge_chunks
                WHERE paper_id = ?
                """,
                (paper_id,),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _get_existing_paper(self, paper_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT paper_id, status, pdf_path, created_at
                FROM papers
                WHERE paper_id = ?
                """,
                (paper_id,),
            ).fetchone()

    def _memory_candidate_from_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "candidate_type": row["candidate_type"],
            "category": row["category"],
            "subject": row["subject"],
            "predicate": row["predicate"],
            "object": row["object"],
            "summary": row["summary"],
            "source_log_ids": self._from_json(row["source_log_ids_json"]),
            "evidence_count": row["evidence_count"],
            "score": row["score"],
            "status": row["status"],
            "created_at": row["created_at"],
            "reviewed_at": row["reviewed_at"],
        }

    def _semantic_memory_from_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "category": row["category"],
            "subject": row["subject"],
            "predicate": row["predicate"],
            "object": row["object"],
            "summary": row["summary"],
            "confidence": row["confidence"],
            "support_count": row["support_count"],
            "supporting_log_ids": self._from_json(row["supporting_log_ids_json"]),
            "status": row["status"],
            "last_confirmed_at": row["last_confirmed_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _normalize_doi(doi: str | None) -> str | None:
        if not doi:
            return None

        normalized = doi.strip().lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break

        return normalized or None

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _to_json(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _from_json(value: str) -> object:
        return json.loads(value)
