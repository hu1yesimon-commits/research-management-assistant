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

    def build_memory_context(self, limit: int = 20) -> str:
        logs = self.list_experiment_logs(limit=limit)
        lines = []
        for log in logs:
            tags = ",".join(log.get("tags", []))
            lines.append(f"{tags}: {log['content']}")
        return "\n".join(lines)

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
