from services.qa_service import QAServiceError
from services.research_assistant_workflow import ResearchAssistantWorkflowError, ResearchAssistantWorkflowService
from services.schemas import (
    ExperimentLogRequest,
    IdeaDiscoverySection,
    IdeaKnowledgeSection,
    IdeaOption,
    IdeaRecommendResponse,
    KnowledgeAnswerResponse,
    KnowledgeAnswerSource,
)


class FakeStore:
    def __init__(self, memory_context: str = ""):
        self.memory_context = memory_context

    def build_memory_context(self) -> str:
        return self.memory_context


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
                    text="embedded graph reconstruction chunk",
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


class FakeIdeaService:
    def __init__(self):
        self.calls = []

    def recommend(
        self,
        experiment_log: ExperimentLogRequest,
        save_log: bool = True,
        include_discovery: bool = False,
        top_k: int = 5,
        idea_count: int = 3,
    ) -> IdeaRecommendResponse:
        self.calls.append((experiment_log, save_log, include_discovery, top_k, idea_count))
        return IdeaRecommendResponse(
            log_id=1 if save_log else None,
            query=" ".join([experiment_log.task, experiment_log.goal]),
            knowledge=IdeaKnowledgeSection(sources=[]),
            discovery=IdeaDiscoverySection(enabled=include_discovery, candidates=[]),
            ideas=[
                IdeaOption(
                    title="Try calibrated retrieval",
                    rationale="Use the experiment log and memory context.",
                    supporting_evidence=[],
                    expected_benefit="Improve precision.",
                    risk="May overfit validation data.",
                    suggested_validation_metric="PRAUC",
                    next_small_experiment="Run one calibration sweep.",
                )
            ],
            mode="deterministic",
        )


def make_log() -> ExperimentLogRequest:
    return ExperimentLogRequest(
        task="graph reconstruction",
        model="GCN",
        dataset="citation graph",
        metric_problem="precision is low",
        tried_methods=["focal loss"],
        observation="recall improves but precision drops",
        goal="improve graph reconstruction precision",
        tags=["graph"],
    )


def build_service(
    store: FakeStore | None = None,
    discovery_graph: FakeDiscoveryGraph | None = None,
    knowledge_service: FakeKnowledgeQAService | None = None,
    idea_service: FakeIdeaService | None = None,
) -> ResearchAssistantWorkflowService:
    return ResearchAssistantWorkflowService(
        store=store or FakeStore(),
        discovery_graph=discovery_graph or FakeDiscoveryGraph(),
        knowledge_qa_service=knowledge_service or FakeKnowledgeQAService(),
        idea_service=idea_service or FakeIdeaService(),
    )


def test_auto_low_coverage_routes_to_basic_explore():
    knowledge = FakeKnowledgeQAService(
        response=KnowledgeAnswerResponse(
            question="new topic",
            answer="No relevant knowledge chunks were found.",
            sources=[],
            mode="deterministic",
        )
    )
    service = build_service(store=FakeStore("Confirmed semantic memory:\nRecent episodic memory:"), knowledge_service=knowledge)

    response = service.query(query="brand new topic", intent="auto", top_k=3)

    assert response.mode == "basic"
    assert response.route == "basic_explore"
    assert response.discovery.candidates[0]["paper"]["paper_id"] == "d1"
    assert response.knowledge.answer == "No relevant knowledge chunks were found."
    assert knowledge.calls == [("brand new topic", 3)]
    assert response.next_action is not None
    assert response.next_action.type == "upload_pdf"


def test_auto_high_coverage_routes_to_advanced_ready_without_running_discovery():
    discovery = FakeDiscoveryGraph()
    knowledge = FakeKnowledgeQAService()
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        discovery_graph=discovery,
        knowledge_service=knowledge,
    )

    response = service.query(query="graph reconstruction precision", intent="auto", top_k=5)

    assert response.mode == "advanced"
    assert response.route == "advanced_ready"
    assert response.discovery.enabled is False
    assert response.knowledge.enabled is False
    assert discovery.calls == []
    assert knowledge.calls == [("graph reconstruction precision", 5)]
    assert response.next_action is not None
    assert response.next_action.type == "choose_intent"


def test_search_intent_routes_to_advanced_search_and_preserves_partial_discovery_failure():
    knowledge = FakeKnowledgeQAService()
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        discovery_graph=FakeDiscoveryGraph(error=RuntimeError("discovery offline")),
        knowledge_service=knowledge,
    )

    response = service.query(query="graph reconstruction precision", intent="search", top_k=5)

    assert response.mode == "advanced"
    assert response.route == "advanced_search"
    assert response.discovery.error == "discovery offline"
    assert response.knowledge.answer == "Knowledge answer"
    assert response.errors[0].section == "discovery"
    assert knowledge.calls == [("graph reconstruction precision", 5)]


def test_search_intent_reuses_coverage_knowledge_failure_without_retrying():
    knowledge = FakeKnowledgeQAService(error=QAServiceError("knowledge offline"))
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        knowledge_service=knowledge,
    )

    response = service.query(query="graph reconstruction precision", intent="search", top_k=5)

    assert response.route == "advanced_search"
    assert response.knowledge.enabled is True
    assert response.knowledge.error == "knowledge offline"
    assert response.errors[0].section == "knowledge"
    assert response.errors[0].message == "knowledge offline"
    assert knowledge.calls == [("graph reconstruction precision", 5)]


def test_research_intent_requires_experiment_log():
    service = build_service()

    try:
        service.query(query="graph reconstruction", intent="research", experiment_log=None)
    except ResearchAssistantWorkflowError as exc:
        assert exc.status_code == 400
        assert "experiment_log is required" in exc.detail
    else:
        raise AssertionError("expected ResearchAssistantWorkflowError")


def test_research_intent_routes_to_idea_service():
    idea_service = FakeIdeaService()
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        idea_service=idea_service,
    )

    response = service.query(query="graph reconstruction precision", intent="research", experiment_log=make_log())

    assert response.mode == "advanced"
    assert response.route == "research_idea"
    assert response.ideas[0].title == "Try calibrated retrieval"
    assert len(idea_service.calls) == 1
