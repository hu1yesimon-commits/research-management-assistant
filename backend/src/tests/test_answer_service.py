from services.answer_service import (
    FakeGroundedAnswerGenerator,
    LLMAnswerGenerator,
    PromptBuilder,
)
from services.schemas import KnowledgeSearchResult


def test_fake_grounded_answer_generator_returns_deterministic_answer_with_sources():
    generator = FakeGroundedAnswerGenerator()
    chunks = [
        KnowledgeSearchResult(
            paper_id="paper-1",
            chunk_index=0,
            text="Graph reconstruction methods rely on structural priors.",
            vector_ref="chroma:research_chunks:paper-1:0:hash-a",
            distance=0.1,
            title="Paper One",
        ),
        KnowledgeSearchResult(
            paper_id="paper-2",
            chunk_index=1,
            text="Recent work emphasizes interpretable retrieval pipelines.",
            vector_ref="chroma:research_chunks:paper-2:1:hash-b",
            distance=0.2,
            title="Paper Two",
        ),
    ]

    answer = generator.generate("How should I approach graph reconstruction?", chunks)

    assert answer == (
        "Grounded answer for 'How should I approach graph reconstruction?': "
        "[1] Paper One chunk 0 says: Graph reconstruction methods rely on structural priors. "
        "[2] Paper Two chunk 1 says: Recent work emphasizes interpretable retrieval pipelines."
    )


def test_prompt_builder_includes_question_numbered_sources_and_grounding_constraints():
    prompt = PromptBuilder().build(
        question="How should I approach graph reconstruction?",
        retrieved_chunks=[
            KnowledgeSearchResult(
                paper_id="paper-1",
                chunk_index=0,
                text="Graph reconstruction methods rely on structural priors.",
                vector_ref="chroma:research_chunks:paper-1:0:hash-a",
                distance=0.1,
                title="Paper One",
            ),
            KnowledgeSearchResult(
                paper_id="paper-2",
                chunk_index=1,
                text="Recent work emphasizes interpretable retrieval pipelines.",
                vector_ref="chroma:research_chunks:paper-2:1:hash-b",
                distance=0.2,
                title="Paper Two",
            ),
        ],
    )

    assert "Question: How should I approach graph reconstruction?" in prompt
    assert "[1] Paper One (paper_id=paper-1, chunk_index=0)" in prompt
    assert "[2] Paper Two (paper_id=paper-2, chunk_index=1)" in prompt
    assert "Graph reconstruction methods rely on structural priors." in prompt
    assert "Recent work emphasizes interpretable retrieval pipelines." in prompt
    assert "Answer using only the sources below." in prompt
    assert "If the sources are insufficient, say that you do not know." in prompt


class FakeLLMClient:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[str] = []

    def invoke(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response


def test_llm_answer_generator_uses_client_and_returns_text_response():
    client = FakeLLMClient("Use structural priors and retrieval grounding.")
    generator = LLMAnswerGenerator(llm_client=client, prompt_builder=PromptBuilder())
    chunks = [
        KnowledgeSearchResult(
            paper_id="paper-1",
            chunk_index=0,
            text="Graph reconstruction methods rely on structural priors.",
            vector_ref="chroma:research_chunks:paper-1:0:hash-a",
            distance=0.1,
            title="Paper One",
        )
    ]

    answer = generator.generate("How should I approach graph reconstruction?", chunks)

    assert answer == "Use structural priors and retrieval grounding."
    assert len(client.calls) == 1
    assert "Question: How should I approach graph reconstruction?" in client.calls[0]


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


def test_llm_answer_generator_reads_content_from_message_objects():
    client = FakeLLMClient(FakeMessage("Answer from message content."))
    generator = LLMAnswerGenerator(llm_client=client, prompt_builder=PromptBuilder())

    answer = generator.generate(
        "What does the source say?",
        [
            KnowledgeSearchResult(
                paper_id="paper-1",
                chunk_index=0,
                text="A source chunk.",
                vector_ref="chroma:research_chunks:paper-1:0:hash-a",
                distance=0.1,
                title="Paper One",
            )
        ],
    )

    assert answer == "Answer from message content."
