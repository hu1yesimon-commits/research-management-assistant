from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.schemas import KnowledgeSearchResult


class AnswerGenerator(Protocol):
    def generate(self, question: str, retrieved_chunks: list[KnowledgeSearchResult]) -> str:
        """Generate a grounded answer from retrieved chunks."""


class FakeGroundedAnswerGenerator:
    def generate(self, question: str, retrieved_chunks: list[KnowledgeSearchResult]) -> str:
        parts = [f"Grounded answer for '{question}':"]
        for index, chunk in enumerate(retrieved_chunks, start=1):
            title = chunk.title or chunk.paper_id
            parts.append(f"[{index}] {title} chunk {chunk.chunk_index} says: {chunk.text}")
        return " ".join(parts)


@dataclass
class PromptBuilder:
    def build(self, question: str, retrieved_chunks: list[KnowledgeSearchResult]) -> str:
        sources: list[str] = []
        for index, chunk in enumerate(retrieved_chunks, start=1):
            title = chunk.title or chunk.paper_id
            sources.append(
                f"[{index}] {title} (paper_id={chunk.paper_id}, chunk_index={chunk.chunk_index})\n"
                f"{chunk.text}"
            )

        source_block = "\n\n".join(sources)
        return (
            "You are answering a research question using retrieved knowledge chunks.\n"
            "Answer using only the sources below.\n"
            "If the sources are insufficient, say that you do not know.\n"
            "Do not use outside knowledge and do not invent citations or source details.\n\n"
            f"Question: {question}\n\n"
            "Sources:\n"
            f"{source_block}"
        )


@dataclass
class LLMAnswerGenerator:
    llm_client: object
    prompt_builder: PromptBuilder

    def generate(self, question: str, retrieved_chunks: list[KnowledgeSearchResult]) -> str:
        prompt = self.prompt_builder.build(question, retrieved_chunks)
        response = self.llm_client.invoke(prompt)
        content = getattr(response, "content", response)
        if isinstance(content, str):
            return content.strip()
        return str(content).strip()
