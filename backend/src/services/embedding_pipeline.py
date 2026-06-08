from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.embedding_service import EmbeddingService
from services.knowledge_base import KnowledgeBase
from services.memory_store import MemoryStore
from services.schemas import PaperStatus
from services.vector_store import VectorStoreService, build_chunk_uid


class EmbeddingPipelineError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass
class EmbeddingPipelineService:
    store: MemoryStore
    knowledge_base: KnowledgeBase
    embedding_service: EmbeddingService
    vector_store_service: VectorStoreService

    def run(self, paper_id: str) -> dict:
        paper = self.store.get_paper(paper_id)
        if paper is None:
            raise EmbeddingPipelineError(f"paper not found: {paper_id}", status_code=404)

        if paper["status"] == PaperStatus.uploaded.value:
            return self._run_phase_2c(paper_id, paper)

        if paper["status"] == PaperStatus.chunked.value:
            return self._run_phase_2d(paper_id)

        raise EmbeddingPipelineError(f"paper is not uploaded or chunked: {paper_id}")

    def _run_phase_2c(self, paper_id: str, paper: dict) -> dict:
        if not paper["pdf_path"]:
            raise EmbeddingPipelineError(f"paper pdf_path missing: {paper_id}")
        if not Path(paper["pdf_path"]).exists():
            raise EmbeddingPipelineError(f"paper pdf_path does not exist: {paper['pdf_path']}")

        try:
            text = self.knowledge_base.extract_text(paper["pdf_path"])
            chunks = self.knowledge_base.chunk_text(text)
        except ValueError as exc:
            raise EmbeddingPipelineError(str(exc)) from exc

        if not chunks:
            raise EmbeddingPipelineError(f"no chunks produced for paper: {paper_id}")

        self.store.delete_knowledge_chunks_by_paper(paper_id)
        self.store.insert_knowledge_chunks(paper_id, chunks)
        self.store.update_paper_status(paper_id, PaperStatus.chunked.value)
        return {
            "paper_id": paper_id,
            "status": PaperStatus.chunked.value,
            "pdf_path": paper["pdf_path"],
            "chunk_count": len(chunks),
        }

    def _run_phase_2d(self, paper_id: str) -> dict:
        chunks = self.store.list_knowledge_chunks(paper_id)
        if not chunks:
            raise EmbeddingPipelineError(f"no persisted chunks for paper: {paper_id}")

        stale_vector_refs = [
            chunk["vector_ref"]
            for chunk in chunks
            if chunk["vector_ref"] is not None and chunk["vector_ref"].strip() != ""
        ]
        new_vector_refs: list[str] = []

        try:
            if stale_vector_refs:
                self.vector_store_service.delete_vector_refs(stale_vector_refs)

            self.store.clear_knowledge_chunk_vector_refs(paper_id)
            embeddings = self.embedding_service.embed_texts([chunk["text"] for chunk in chunks])
            if len(embeddings) != len(chunks):
                raise EmbeddingPipelineError(f"embedding count mismatch for paper: {paper_id}")

            vector_chunks = [
                {
                    "paper_id": paper_id,
                    "chunk_index": chunk["chunk_index"],
                    "chunk_hash": chunk["chunk_hash"],
                    "chunk_uid": build_chunk_uid(paper_id, chunk["chunk_index"], chunk["chunk_hash"]),
                    "text": chunk["text"],
                }
                for chunk in chunks
            ]
            new_vector_refs = self.vector_store_service.upsert_chunks(vector_chunks, embeddings)
            if len(new_vector_refs) != len(chunks):
                raise EmbeddingPipelineError(f"vector ref count mismatch for paper: {paper_id}")

            self.store.update_knowledge_chunk_vector_refs(
                paper_id,
                [
                    {
                        "chunk_index": chunk["chunk_index"],
                        "vector_ref": vector_ref,
                    }
                    for chunk, vector_ref in zip(chunks, new_vector_refs, strict=True)
                ],
            )

            if not self.store.has_complete_knowledge_chunk_vector_refs(paper_id):
                raise EmbeddingPipelineError(f"incomplete vector refs for paper: {paper_id}")

            self.store.update_paper_status(paper_id, PaperStatus.embedded.value)
            return {
                "paper_id": paper_id,
                "status": PaperStatus.embedded.value,
                "vector_ref_count": len(new_vector_refs),
            }
        except ValueError as exc:
            self.store.clear_knowledge_chunk_vector_refs(paper_id)
            if new_vector_refs:
                self.vector_store_service.delete_vector_refs(new_vector_refs)
            raise EmbeddingPipelineError(str(exc)) from exc
        except EmbeddingPipelineError:
            self.store.clear_knowledge_chunk_vector_refs(paper_id)
            if new_vector_refs:
                self.vector_store_service.delete_vector_refs(new_vector_refs)
            raise
