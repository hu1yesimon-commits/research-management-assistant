from services.qa_service import QAServiceError
from services.research_workflow import ResearchWorkflowError, ResearchWorkflowService
from services.schemas import KnowledgeAnswerResponse, KnowledgeAnswerSource


class FakeDiscoveryGraph:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result if result is not None else [{"paper": {"paper_id": "d1", "title": "Discovery Paper"}}]
        self.error = error
        self.calls: list[dict] = []

    def invoke(self, state: dict) -> dict:
        self.calls.append(state)
        if self.error is not None:
            raise self.error
        return {**state, "ranked_candidates": self.result}


class FakeKnowledgeQAService:
    def __init__(self, response: KnowledgeAnswerResponse | None = None, error: Exception | None = None):
        self.response = response or KnowledgeAnswerResponse(
            question="graph reconstruction",
            answer="Knowledge answer",
            sources=[
                KnowledgeAnswerSource(
                    paper_id="k1",
                    title="Knowledge Paper",
                    chunk_index=0,
                    distance=0.1,
                    text="embedded chunk",
                    vector_ref="chroma:research_chunks:k1:0:hash",
                )
            ],
            mode="deterministic",
        )
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def answer(self, question: str, top_k: int = 5) -> KnowledgeAnswerResponse:
        self.calls.append((question, top_k))
        if self.error is not None:
            raise self.error
        return self.response


def build_service(
    discovery_graph: FakeDiscoveryGraph | None = None,
    knowledge_service: FakeKnowledgeQAService | None = None,
) -> ResearchWorkflowService:
    return ResearchWorkflowService(
        discovery_graph=discovery_graph or FakeDiscoveryGraph(),
        knowledge_qa_service=knowledge_service or FakeKnowledgeQAService(),
    )


def test_research_workflow_returns_discovery_and_knowledge_when_both_enabled():
    service = build_service()

    response = service.query("lightweight graph reconstruction", mode="basic", top_k=5)

    assert response.query == "lightweight graph reconstruction"
    assert response.mode == "basic"
    assert response.discovery.enabled is True
    assert response.discovery.error is None
    assert response.discovery.candidates[0]["paper"]["paper_id"] == "d1"
    assert response.knowledge.enabled is True
    assert response.knowledge.answer == "Knowledge answer"
    assert response.knowledge.sources[0].paper_id == "k1"


def test_research_workflow_limits_discovery_candidates_to_top_k():
    discovery_graph = FakeDiscoveryGraph(
        result=[
            {"paper": {"paper_id": "d1", "title": "Discovery Paper 1"}},
            {"paper": {"paper_id": "d2", "title": "Discovery Paper 2"}},
            {"paper": {"paper_id": "d3", "title": "Discovery Paper 3"}},
            {"paper": {"paper_id": "d4", "title": "Discovery Paper 4"}},
        ]
    )
    knowledge_service = FakeKnowledgeQAService()
    service = build_service(discovery_graph=discovery_graph, knowledge_service=knowledge_service)

    response = service.query(
        "lightweight graph reconstruction",
        include_discovery=True,
        include_knowledge=False,
        top_k=3,
    )

    assert [candidate["paper"]["paper_id"] for candidate in response.discovery.candidates] == ["d1", "d2", "d3"]
    assert knowledge_service.calls == []


def test_research_workflow_only_discovery_enabled_does_not_call_knowledge():
    discovery_graph = FakeDiscoveryGraph()
    knowledge_service = FakeKnowledgeQAService()
    service = build_service(discovery_graph=discovery_graph, knowledge_service=knowledge_service)

    response = service.query(
        "lightweight graph reconstruction",
        mode="advanced",
        include_discovery=True,
        include_knowledge=False,
        top_k=3,
    )

    assert len(discovery_graph.calls) == 1
    assert knowledge_service.calls == []
    assert response.discovery.enabled is True
    assert response.knowledge.enabled is False
    assert response.knowledge.answer is None


def test_research_workflow_only_knowledge_enabled_does_not_call_discovery():
    discovery_graph = FakeDiscoveryGraph()
    knowledge_service = FakeKnowledgeQAService()
    service = build_service(discovery_graph=discovery_graph, knowledge_service=knowledge_service)

    response = service.query(
        "lightweight graph reconstruction",
        include_discovery=False,
        include_knowledge=True,
        top_k=4,
    )

    assert discovery_graph.calls == []
    assert len(knowledge_service.calls) == 1
    assert response.discovery.enabled is False
    assert response.discovery.candidates == []
    assert response.knowledge.enabled is True
    assert response.knowledge.answer == "Knowledge answer"
    assert knowledge_service.calls == [("lightweight graph reconstruction", 4)]


def test_research_workflow_rejects_when_both_sections_disabled():
    service = build_service()

    try:
        service.query(
            "lightweight graph reconstruction",
            include_discovery=False,
            include_knowledge=False,
        )
    except ResearchWorkflowError as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("expected ResearchWorkflowError")


def test_research_workflow_discovery_failure_keeps_knowledge_section():
    service = build_service(
        discovery_graph=FakeDiscoveryGraph(error=RuntimeError("discovery failed")),
        knowledge_service=FakeKnowledgeQAService(),
    )

    response = service.query("lightweight graph reconstruction", include_discovery=True, include_knowledge=True)

    assert response.discovery.enabled is True
    assert response.discovery.candidates == []
    assert response.discovery.error == "discovery failed"
    assert response.knowledge.answer == "Knowledge answer"
    assert response.knowledge.error is None


def test_research_workflow_knowledge_failure_keeps_discovery_section():
    service = build_service(
        discovery_graph=FakeDiscoveryGraph(),
        knowledge_service=FakeKnowledgeQAService(error=QAServiceError("knowledge failed", status_code=400)),
    )

    response = service.query("lightweight graph reconstruction", include_discovery=True, include_knowledge=True)

    assert response.discovery.enabled is True
    assert response.discovery.error is None
    assert response.discovery.candidates[0]["paper"]["paper_id"] == "d1"
    assert response.knowledge.enabled is True
    assert response.knowledge.answer is None
    assert response.knowledge.sources == []
    assert response.knowledge.error == "knowledge failed"
