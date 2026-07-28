from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.schemas import KnowledgeSearchResult


class AnswerGenerator(Protocol):
    def generate(self, question: str, retrieved_chunks: list[KnowledgeSearchResult]) -> str:
        """Generate a grounded answer from retrieved chunks."""


class FakeGroundedAnswerGenerator:
    max_sources: int = 3
    max_snippet_chars: int = 160

    def generate(self, question: str, retrieved_chunks: list[KnowledgeSearchResult]) -> str:
        count = len(retrieved_chunks)
        noun = "chunk" if count == 1 else "chunks"
        source_labels = [
            f"{chunk.title or chunk.paper_id} chunk {chunk.chunk_index}"
            for chunk in retrieved_chunks[: self.max_sources]
        ]
        source_summary = "; ".join(source_labels)
        snippets = [
            self._snippet(chunk.text)
            for chunk in retrieved_chunks[:2]
            if chunk.text.strip()
        ]
        evidence_hint = " ".join(snippets)
        if evidence_hint:
            evidence_hint = f" Evidence highlights: {evidence_hint}"
        return (
            f"I found {count} saved knowledge {noun} relevant to '{question}'. "
            f"Main sources: {source_summary}.{evidence_hint} "
            "Open the Knowledge panel for the full evidence and source chunks."
        )

    def _snippet(self, text: str) -> str:
        compact = " ".join(text.split())
        if len(compact) <= self.max_snippet_chars:
            return compact
        return f"{compact[: self.max_snippet_chars].rstrip()}..."


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
            "Keep the answer concise and user-friendly.\n"
            "Cite source numbers like [1] when making evidence-backed claims.\n"
            "Do not quote or repeat long source passages.\n"
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
