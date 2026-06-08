from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any
from typing import Protocol


class EmbeddingService(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""


class FakeEmbeddingService:
    VECTOR_SIZE = 4

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector = []
        for offset in range(self.VECTOR_SIZE):
            chunk = digest[offset * 4 : (offset + 1) * 4]
            raw_value = int.from_bytes(chunk, byteorder="big", signed=False)
            vector.append(raw_value / 4294967295.0)
        return vector


@dataclass
class BgeM3EmbeddingService:
    model_name: str = "BAAI/bge-m3"
    model: Any = field(init=False)

    def __post_init__(self) -> None:
        self.model = self._load_model()

    def _load_model(self):
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self.model_name)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors = self.model.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in vector] for vector in vectors]
