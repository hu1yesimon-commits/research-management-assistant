from __future__ import annotations

from dataclasses import dataclass

from services.embedding_service import EmbeddingService
from services.memory_store import MemoryStore
from services.schemas import KnowledgeSearchResponse, KnowledgeSearchResult
from services.vector_store import VectorStoreService


class RetrievalServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass
class KnowledgeRetrievalService:
    store: MemoryStore
    embedding_service: EmbeddingService
    vector_store_service: VectorStoreService

    def search(self, query: str, top_k: int = 5) -> KnowledgeSearchResponse:
        normalized_query = query.strip()
        if not normalized_query:
            raise RetrievalServiceError("query must not be empty", status_code=400)

        query_embedding = self.embedding_service.embed_texts([normalized_query])[0]
        vector_hits = self.vector_store_service.query_by_embedding(query_embedding, top_k=top_k)

        results = []
        for hit in vector_hits:
            chunk = self.store.get_knowledge_chunk(hit.paper_id, hit.chunk_index)
            paper = self.store.get_paper(hit.paper_id)
            if chunk is None or paper is None:
                continue
            if paper["status"] != "embedded":
                continue
            if not chunk["vector_ref"] or chunk["vector_ref"] != hit.vector_ref:
                continue

            results.append(
                KnowledgeSearchResult(
                    paper_id=hit.paper_id,
                    chunk_index=hit.chunk_index,
                    text=chunk["text"],
                    vector_ref=chunk["vector_ref"],
                    distance=hit.distance,
                    title=paper["title"],
                )
            )

        return KnowledgeSearchResponse(query=normalized_query, top_k=top_k, results=results)
