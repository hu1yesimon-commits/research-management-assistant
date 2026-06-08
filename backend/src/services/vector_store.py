from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from typing import Protocol


def build_chunk_uid(paper_id: str, chunk_index: int, chunk_hash: str) -> str:
    return f"{paper_id}:{chunk_index}:{chunk_hash}"


class VectorStoreService(Protocol):
    def upsert_chunks(self, chunks: list[dict], embeddings: list[list[float]]) -> list[str]:
        """Write vectors and return vector_ref receipts."""

    def delete_vector_refs(self, vector_refs: list[str]) -> None:
        """Delete previously written vectors by receipt."""

    def query_by_embedding(self, embedding: list[float], top_k: int) -> list["VectorSearchResult"]:
        """Return the nearest chunk hits for the query embedding."""


@dataclass
class VectorSearchResult:
    chunk_uid: str
    vector_ref: str
    distance: float
    paper_id: str
    chunk_index: int


def build_vector_ref(collection_name: str, chunk_uid: str) -> str:
    return f"chroma:{collection_name}:{chunk_uid}"


def parse_vector_ref(vector_ref: str) -> tuple[str, str]:
    prefix = "chroma:"
    if not vector_ref.startswith(prefix):
        raise ValueError(f"unsupported vector_ref: {vector_ref}")

    remainder = vector_ref[len(prefix) :]
    collection_name, separator, chunk_uid = remainder.partition(":")
    if not separator or not collection_name or not chunk_uid:
        raise ValueError(f"invalid vector_ref: {vector_ref}")
    return collection_name, chunk_uid


@dataclass
class FakeVectorStoreService:
    collection_name: str = "research_chunks"
    records: dict[str, dict] = field(default_factory=dict)

    def upsert_chunks(self, chunks: list[dict], embeddings: list[list[float]]) -> list[str]:
        vector_refs = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            vector_ref = build_vector_ref(self.collection_name, chunk["chunk_uid"])
            self.records[vector_ref] = {
                "chunk": chunk,
                "embedding": embedding,
            }
            vector_refs.append(vector_ref)
        return vector_refs

    def delete_vector_refs(self, vector_refs: list[str]) -> None:
        for vector_ref in vector_refs:
            self.records.pop(vector_ref, None)

    def query_by_embedding(self, embedding: list[float], top_k: int) -> list[VectorSearchResult]:
        results = []
        for vector_ref, record in self.records.items():
            stored_embedding = record["embedding"]
            distance = sum((float(left) - float(right)) ** 2 for left, right in zip(embedding, stored_embedding, strict=True))
            chunk = record["chunk"]
            results.append(
                VectorSearchResult(
                    chunk_uid=chunk["chunk_uid"],
                    vector_ref=vector_ref,
                    distance=distance,
                    paper_id=chunk["paper_id"],
                    chunk_index=chunk["chunk_index"],
                )
            )

        results.sort(key=lambda item: (item.distance, item.chunk_uid))
        return results[:top_k]


@dataclass
class ChromaVectorStoreService:
    persist_dir: str
    collection_name: str = "research_chunks"
    client: Any = field(init=False)
    collection: Any = field(init=False)

    def __post_init__(self) -> None:
        from chromadb import PersistentClient

        persist_path = Path(self.persist_dir)
        persist_path.mkdir(parents=True, exist_ok=True)
        self.client = PersistentClient(path=str(persist_path))
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def upsert_chunks(self, chunks: list[dict], embeddings: list[list[float]]) -> list[str]:
        if len(chunks) != len(embeddings):
            raise ValueError("chunk count does not match embedding count")
        if not chunks:
            return []

        ids = [chunk["chunk_uid"] for chunk in chunks]
        documents = [chunk["text"] for chunk in chunks]
        metadatas = [
            {
                "paper_id": chunk.get("paper_id"),
                "chunk_index": chunk.get("chunk_index"),
                "chunk_hash": chunk.get("chunk_hash"),
            }
            for chunk in chunks
        ]

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        return [build_vector_ref(self.collection_name, chunk_uid) for chunk_uid in ids]

    def delete_vector_refs(self, vector_refs: list[str]) -> None:
        ids = []
        for vector_ref in vector_refs:
            collection_name, chunk_uid = parse_vector_ref(vector_ref)
            if collection_name != self.collection_name:
                continue
            ids.append(chunk_uid)

        if ids:
            self.collection.delete(ids=ids)

    def query_by_embedding(self, embedding: list[float], top_k: int) -> list[VectorSearchResult]:
        payload = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["metadatas", "distances"],
        )

        ids = payload.get("ids", [[]])[0]
        metadatas = payload.get("metadatas", [[]])[0]
        distances = payload.get("distances", [[]])[0]

        results = []
        for chunk_uid, metadata, distance in zip(ids, metadatas, distances, strict=True):
            paper_id, chunk_index, _ = chunk_uid.split(":", 2)
            metadata = metadata or {}
            results.append(
                VectorSearchResult(
                    chunk_uid=chunk_uid,
                    vector_ref=build_vector_ref(self.collection_name, chunk_uid),
                    distance=float(distance),
                    paper_id=str(metadata.get("paper_id") or paper_id),
                    chunk_index=int(metadata.get("chunk_index") if metadata.get("chunk_index") is not None else chunk_index),
                )
            )
        return results
