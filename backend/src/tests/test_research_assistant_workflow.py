import pytest

from graph.errors import DiscoveryStageError
from services.idea_service import IdeaServiceError
from services.qa_service import KnowledgeQAService, QAServiceError
from services.retrieval_service import RetrievalServiceError
from services.research_assistant_workflow import ResearchAssistantWorkflowError, ResearchAssistantWorkflowService
from services.schemas import (
    AssistantStageError,
    DiscoveryResult,
    ExperimentLogRequest,
    IdeaDiscoverySection,
    IdeaKnowledgeSection,
    IdeaOption,
    IdeaRecommendResponse,
    KnowledgeAnswerResponse,
    KnowledgeAnswerSource,
    KnowledgeResult,
    KnowledgeSearchResponse,
    KnowledgeSearchResult,
    NextActionOption,
    ResearchAssistantNextAction,
)


class FakeStore:
    def __init__(self, memory_context: str = ""):
        self.memory_context = memory_context

    def build_memory_context(self) -> str:
        return self.memory_context


class FakeDiscoveryGraph:
    def __init__(
        self,
        result=None,
        error: Exception | None = None,
        rewritten_queries: list[str] | None = None,
        raw_results: list | None = None,
        deduped_papers: list | None = None,
        judge_failures: list[str] | None = None,
    ):
        self.result = result if result is not None else [{"paper": {"paper_id": "d1", "title": "Discovery Paper"}}]
        self.error = error
        self.rewritten_queries = rewritten_queries
        self.raw_results = raw_results
        self.deduped_papers = deduped_papers
        self.judge_failures = judge_failures
        self.calls: list[dict] = []

    def invoke(self, state: dict) -> dict:
        self.calls.append(state)
        if self.error is not None:
            raise self.error
        return {
            **state,
            "rewritten_queries": (
                self.rewritten_queries if self.rewritten_queries is not None else state["rewritten_queries"]
            ),
            "raw_results": self.raw_results if self.raw_results is not None else state["raw_results"],
            "deduped_papers": (
                self.deduped_papers if self.deduped_papers is not None else state["deduped_papers"]
            ),
            "judge_failures": self.judge_failures if self.judge_failures is not None else state.get("judge_failures", []),
            "ranked_candidates": self.result,
        }


class RankedOnlyDiscoveryGraph:
    def __init__(self, ranked_candidates: list[dict]):
        self.ranked_candidates = ranked_candidates

    def invoke(self, state: dict) -> dict:
        return {"ranked_candidates": self.ranked_candidates}


class FakeRetrievalService:
    def __init__(self, response: KnowledgeAnswerResponse, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, top_k: int = 5) -> KnowledgeSearchResponse:
        self.calls.append((query, top_k))
        if self.error is not None:
            raise self.error
        return KnowledgeSearchResponse(
            query=query,
            top_k=top_k,
            results=[
                KnowledgeSearchResult(
                    paper_id=source.paper_id,
                    title=source.title,
                    chunk_index=source.chunk_index,
                    distance=source.distance,
                    text=source.text,
                    vector_ref=source.vector_ref,
                )
                for source in self.response.sources
            ],
        )


class FakeKnowledgeQAService:
    def __init__(
        self,
        response: KnowledgeAnswerResponse | None = None,
        error: Exception | None = None,
        retrieval_error: Exception | None = None,
    ):
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
        self.retrieval_service = FakeRetrievalService(self.response, error=retrieval_error)
        self.answer_calls: list[tuple[str, int]] = []

    def answer(
        self,
        question: str,
        top_k: int = 5,
        retrieved_results: list[KnowledgeSearchResult] | None = None,
    ) -> KnowledgeAnswerResponse:
        self.answer_calls.append((question, top_k))
        if self.error is not None:
            raise self.error
        return self.response


class TrackingGroundedAnswerGenerator:
    def __init__(self):
        self.calls: list[tuple[str, list[KnowledgeSearchResult]]] = []

    def generate(self, question: str, retrieved_chunks: list[KnowledgeSearchResult]) -> str:
        self.calls.append((question, retrieved_chunks))
        return "Grounded cached answer"


class FakeIdeaService:
    def __init__(self, error: IdeaServiceError | None = None):
        self.error = error
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
        if self.error is not None:
            raise self.error
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


def test_assistant_v1_result_contracts_have_safe_defaults():
    discovery = DiscoveryResult(enabled=True)
    knowledge = KnowledgeResult(enabled=False)
    error = AssistantStageError(stage="coverage", message="retrieval unavailable")

    assert discovery.top_k == []
    assert discovery.total_raw == 0
    assert knowledge.sources == []
    assert error.recoverable is True


def test_assistant_v1_next_action_supports_structured_options():
    next_action = ResearchAssistantNextAction(
        type="choose_path",
        options=[
            NextActionOption(
                id="continue_search",
                label="Search papers",
                request_patch={"intent": "search"},
            )
        ],
        message="Choose how to continue.",
    )

    assert next_action.options[0].id == "continue_search"
    assert next_action.options[0].request_patch == {"intent": "search"}


def test_next_action_normalization_accepts_legacy_string_options(monkeypatch):
    class LegacyActionGraph:
        def invoke(self, state):
            return {
                **state,
                "next_action": {
                    "type": "upload_pdf",
                    "options": ["review_candidates", "upload_pdf"],
                    "message": "Choose a next step.",
                },
            }

    monkeypatch.setattr(
        "services.research_assistant_workflow.build_research_assistant_graph",
        lambda **_: LegacyActionGraph(),
    )

    next_action = build_service().query("legacy custom graph").next_action

    assert next_action is not None
    assert next_action.options[0] == NextActionOption(
        id="review_candidates",
        label="Review Candidates",
        request_patch={},
    )
    assert next_action.options[1] == NextActionOption(
        id="upload_pdf",
        label="Upload Pdf",
        request_patch={},
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
    assert knowledge.retrieval_service.calls == [("brand new topic", 3)]
    assert knowledge.answer_calls == [("brand new topic", 3)]
    assert response.next_action is not None
    assert response.next_action.type == "upload_pdf"
    assert response.next_action.options[0].id == "review_candidates"
    assert response.next_action.options[0].request_patch == {}
    assert response.next_action.options[1].id == "upload_pdf"
    assert response.next_action.options[1].request_patch == {}


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
    assert response.knowledge.enabled is True
    assert response.knowledge.answer == "Knowledge answer"
    assert response.discovery_result.enabled is False
    assert response.knowledge_result.enabled is True
    assert response.knowledge_result.answer == response.knowledge.answer
    assert response.idea_result.enabled is False
    assert discovery.calls == []
    assert knowledge.retrieval_service.calls == [("graph reconstruction precision", 5)]
    assert knowledge.answer_calls == [("graph reconstruction precision", 5)]
    assert response.next_action is not None
    assert response.next_action.type == "choose_path"
    assert response.next_action.options[0].id == "continue_search"
    assert response.next_action.options[0].request_patch == {"intent": "search"}
    assert response.next_action.options[1].id == "submit_experiment_log"
    assert response.next_action.options[1].request_patch == {"intent": "research"}


def test_advanced_ready_returns_no_source_fallback_when_qa_has_no_sources():
    knowledge = FakeKnowledgeQAService(
        response=KnowledgeAnswerResponse(
            question="graph reconstruction precision",
            answer="No relevant knowledge chunks were found.",
            sources=[],
            mode="deterministic",
        )
    )
    service = build_service(
        store=FakeStore(
            "Confirmed semantic memory: graph reconstruction precision\n"
            "Recent episodic memory: graph reconstruction precision"
        ),
        knowledge_service=knowledge,
    )

    response = service.query(query="graph reconstruction precision", intent="auto", top_k=5)

    assert response.route == "advanced_ready"
    assert response.knowledge.enabled is True
    assert response.knowledge.sources == []
    assert "could not find grounded local sources" in response.assistant_message.lower()
    assert response.next_action is not None
    assert response.next_action.type == "choose_path"


def test_advanced_ready_reports_qa_outage_instead_of_no_sources():
    knowledge = FakeKnowledgeQAService(error=QAServiceError("knowledge provider unavailable", status_code=502))
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        knowledge_service=knowledge,
    )

    response = service.query(query="graph reconstruction precision", intent="auto", top_k=5)

    assert response.route == "advanced_ready"
    assert response.knowledge.enabled is True
    assert response.knowledge.error == "knowledge provider unavailable"
    assert response.errors[0].stage == "knowledge_answer"
    assert "temporarily unavailable" in response.assistant_message.lower()
    assert "could not find grounded local sources" not in response.assistant_message.lower()


def test_advanced_ready_reuses_coverage_results_for_real_qa_service():
    retrieval_response = KnowledgeAnswerResponse(
        question="graph reconstruction precision",
        answer="unused",
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
    retrieval = FakeRetrievalService(retrieval_response)
    generator = TrackingGroundedAnswerGenerator()
    knowledge = KnowledgeQAService(retrieval_service=retrieval, answer_generator=generator)
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        knowledge_service=knowledge,
    )

    response = service.query(query="graph reconstruction precision", intent="auto", top_k=5)

    assert response.route == "advanced_ready"
    assert response.knowledge.answer == "Grounded cached answer"
    assert retrieval.calls == [("graph reconstruction precision", 5)]
    assert len(generator.calls) == 1


def test_experiment_log_triggers_research_idea_even_when_intent_is_auto():
    idea_service = FakeIdeaService()
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        idea_service=idea_service,
    )

    response = service.query(
        query="graph reconstruction precision",
        intent="auto",
        experiment_log=make_log(),
    )

    assert response.route == "research_idea"
    assert len(idea_service.calls) == 1
    assert response.next_action is not None
    assert response.next_action.options[0].id == "select_idea"
    assert response.next_action.options[0].request_patch == {}
    assert response.next_action.options[1].id == "continue_search"
    assert response.next_action.options[1].request_patch == {"intent": "search"}


def test_stored_memory_log_does_not_trigger_research_idea_without_current_request_log():
    idea_service = FakeIdeaService()
    service = build_service(
        store=FakeStore(
            "Confirmed semantic memory: graph reconstruction precision\n"
            "Recent episodic memory: task=graph reconstruction observation=precision drops"
        ),
        idea_service=idea_service,
    )

    response = service.query(query="graph reconstruction precision", intent="auto")

    assert response.route == "advanced_ready"
    assert idea_service.calls == []


def test_assistant_response_initializes_v1_result_fields_alongside_legacy_fields():
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        knowledge_service=FakeKnowledgeQAService(),
    )

    response = service.query(query="graph reconstruction precision", intent="search", top_k=2)

    assert response.discovery.enabled is True
    assert response.knowledge.enabled is True
    assert {
        "discovery_result",
        "knowledge_result",
        "idea_result",
    } <= response.model_fields_set


def test_search_intent_maps_legacy_sections_into_v1_result_fields():
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        knowledge_service=FakeKnowledgeQAService(),
    )

    response = service.query(query="graph reconstruction precision", intent="search", top_k=2)

    assert response.discovery_result.enabled is True
    assert response.knowledge_result.enabled is True
    assert response.idea_result.enabled is False
    assert response.discovery_result.top_k == response.discovery.candidates
    assert response.knowledge_result.answer == response.knowledge.answer


def test_search_intent_passes_exact_assistant_memory_snapshot_to_discovery():
    memory_snapshot = (
        "Confirmed semantic memory: prefers lightweight graph models\n"
        "Recent episodic memory: observation=precision drops"
    )
    discovery = FakeDiscoveryGraph()
    service = build_service(
        store=FakeStore(memory_snapshot),
        discovery_graph=discovery,
    )

    service.query(query="graph reconstruction precision", intent="search", top_k=2)

    assert discovery.calls[0]["memory_context"] == memory_snapshot
    assert discovery.calls[0]["memory_context_is_snapshot"] is True


def test_search_intent_marks_empty_assistant_memory_as_authoritative_snapshot():
    discovery = FakeDiscoveryGraph()
    service = build_service(
        store=FakeStore(""),
        discovery_graph=discovery,
    )

    service.query(query="graph reconstruction", intent="search", top_k=1)

    assert discovery.calls[0]["memory_context"] == ""
    assert discovery.calls[0]["memory_context_is_snapshot"] is True


def test_search_intent_reports_full_discovery_counts_but_exposes_only_top_k():
    ranked_candidates = [
        {"paper": {"paper_id": "d1", "title": "First Discovery Paper"}},
        {"paper": {"paper_id": "d2", "title": "Second Discovery Paper"}},
    ]
    discovery = FakeDiscoveryGraph(
        result=ranked_candidates,
        rewritten_queries=["graph reconstruction", "lightweight graph reconstruction"],
        raw_results=[{"paper_id": "raw-1"}, {"paper_id": "raw-2"}, {"paper_id": "raw-3"}],
        deduped_papers=[{"paper_id": "d1"}, {"paper_id": "d2"}],
    )
    service = build_service(discovery_graph=discovery)

    response = service.query(query="graph reconstruction", intent="search", top_k=1)

    assert response.discovery.candidates == ranked_candidates[:1]
    assert response.discovery_result.top_k == ranked_candidates[:1]
    assert response.discovery_result.rewritten_queries == [
        "graph reconstruction",
        "lightweight graph reconstruction",
    ]
    assert response.discovery_result.total_raw == 3
    assert response.discovery_result.total_deduped == 2
    assert response.discovery_result.scoring_summary == {"ranked_count": 2}
    assert "raw_results" not in response.model_dump()


def test_search_intent_accepts_ranked_only_custom_discovery_graph():
    ranked_candidates = [
        {"paper": {"paper_id": "d1", "title": "First Discovery Paper"}},
        {"paper": {"paper_id": "d2", "title": "Second Discovery Paper"}},
    ]
    service = build_service(
        discovery_graph=RankedOnlyDiscoveryGraph(ranked_candidates),
    )

    response = service.query(query="graph reconstruction", intent="search", top_k=1)

    assert response.discovery_result.top_k == ranked_candidates[:1]
    assert response.discovery_result.rewritten_queries == []
    assert response.discovery_result.total_raw == 0
    assert response.discovery_result.total_deduped == 0
    assert response.discovery_result.scoring_summary == {"ranked_count": 2}


def test_search_intent_routes_to_advanced_search_and_preserves_partial_discovery_failure():
    knowledge = FakeKnowledgeQAService()
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        discovery_graph=FakeDiscoveryGraph(
            error=DiscoveryStageError("multi_search", "discovery offline", recoverable=True)
        ),
        knowledge_service=knowledge,
    )

    response = service.query(query="graph reconstruction precision", intent="search", top_k=5)

    assert response.mode == "advanced"
    assert response.route == "advanced_search"
    assert response.discovery.error == "discovery offline"
    assert response.discovery_result.error == "discovery offline"
    assert response.discovery_result.rewritten_queries == []
    assert response.discovery_result.total_raw == 0
    assert response.discovery_result.total_deduped == 0
    assert response.discovery_result.scoring_summary == {"ranked_count": 0}
    assert response.knowledge.answer == "Knowledge answer"
    assert response.errors[0].stage == "multi_search"
    assert response.errors[0].section == "discovery"
    assert response.errors[0].recoverable is True
    assert knowledge.retrieval_service.calls == [("graph reconstruction precision", 5)]
    assert knowledge.answer_calls == [("graph reconstruction precision", 5)]


def test_search_intent_keeps_legacy_error_section_compatibility():
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        knowledge_service=FakeKnowledgeQAService(error=QAServiceError("knowledge offline")),
    )

    response = service.query(query="graph reconstruction precision", intent="search", top_k=5)

    assert response.errors[0].stage == "knowledge_answer"
    assert response.errors[0].section == "knowledge"


def test_search_intent_surfaces_llm_judge_stage_error_when_discovery_reports_judge_failures():
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        discovery_graph=FakeDiscoveryGraph(
            judge_failures=["judge failed: RuntimeError: synthetic judge failure for paper-broken"]
        ),
    )

    response = service.query(query="graph reconstruction precision", intent="search", top_k=5)

    assert response.route == "advanced_search"
    assert any(error.stage == "llm_judge" for error in response.errors)
    assert any(error.section == "discovery" for error in response.errors)


def test_search_intent_propagates_unknown_discovery_failure():
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        discovery_graph=FakeDiscoveryGraph(error=RuntimeError("unexpected discovery defect")),
    )

    with pytest.raises(RuntimeError, match="unexpected discovery defect"):
        service.query(query="graph reconstruction precision", intent="search", top_k=5)


def test_search_intent_calls_answer_once_when_route_consumes_knowledge():
    knowledge = FakeKnowledgeQAService(error=QAServiceError("knowledge offline"))
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        knowledge_service=knowledge,
    )

    response = service.query(query="graph reconstruction precision", intent="search", top_k=5)

    assert response.route == "advanced_search"
    assert response.knowledge.enabled is True
    assert response.knowledge.error == "knowledge offline"
    assert response.errors[0].stage == "knowledge_answer"
    assert response.errors[0].recoverable is True
    assert response.errors[0].message == "knowledge offline"
    assert knowledge.retrieval_service.calls == [("graph reconstruction precision", 5)]
    assert knowledge.answer_calls == [("graph reconstruction precision", 5)]


def test_auto_coverage_retrieval_failure_routes_to_basic_explore_with_coverage_error():
    knowledge = FakeKnowledgeQAService(
        retrieval_error=RetrievalServiceError("knowledge retrieval failed: vector backend unavailable", status_code=502)
    )
    service = build_service(
        store=FakeStore("Confirmed semantic memory:\nRecent episodic memory:"),
        knowledge_service=knowledge,
    )

    response = service.query(query="graph reconstruction precision", intent="auto", top_k=5)

    assert response.mode == "basic"
    assert response.route == "basic_explore"
    assert response.errors[0].stage == "coverage"
    assert response.errors[0].recoverable is True
    assert response.errors[0].message == "knowledge retrieval failed: vector backend unavailable"
    assert knowledge.retrieval_service.calls == [("graph reconstruction precision", 5)]
    assert knowledge.answer_calls == [("graph reconstruction precision", 5)]


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
    knowledge = FakeKnowledgeQAService()
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        knowledge_service=knowledge,
        idea_service=idea_service,
    )

    response = service.query(query="graph reconstruction precision", intent="research", experiment_log=make_log())

    assert response.mode == "advanced"
    assert response.route == "research_idea"
    assert response.ideas[0].title == "Try calibrated retrieval"
    assert len(idea_service.calls) == 1
    assert knowledge.answer_calls == []


def test_research_intent_maps_client_idea_failure_to_nonrecoverable_result():
    service = build_service(
        idea_service=FakeIdeaService(error=IdeaServiceError("invalid experiment log", status_code=400))
    )

    response = service.query(
        query="graph reconstruction precision",
        intent="research",
        experiment_log=make_log(),
    )

    assert response.ideas == []
    assert response.discovery.enabled is False
    assert response.knowledge.enabled is False
    assert response.discovery_result.enabled is False
    assert response.knowledge_result.enabled is False
    assert response.idea_result.enabled is True
    assert response.idea_result.error == "invalid experiment log"
    assert response.errors[0].stage == "idea_generation"
    assert response.errors[0].recoverable is False


def test_research_intent_maps_server_idea_failure_to_recoverable_result():
    service = build_service(
        idea_service=FakeIdeaService(error=IdeaServiceError("idea provider unavailable", status_code=502))
    )

    response = service.query(
        query="graph reconstruction precision",
        intent="research",
        experiment_log=make_log(),
    )

    assert response.ideas == []
    assert response.discovery.enabled is False
    assert response.knowledge.enabled is False
    assert response.discovery_result.enabled is False
    assert response.knowledge_result.enabled is False
    assert response.idea_result.enabled is True
    assert response.idea_result.error == "idea provider unavailable"
    assert response.errors[0].stage == "idea_generation"
    assert response.errors[0].recoverable is True
