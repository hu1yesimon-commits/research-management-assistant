import pytest

from agent_team.idea_agent import IdeaAgent
from agent_team.research_agent import ResearchAgent
from graph.errors import DiscoveryStageError
from services.candidate_lifecycle import CandidateLifecycleService
from services.idea_service import IdeaServiceError
from services.memory_store import MemoryStore
from services.schemas import (
    ExperimentLogRequest,
    IdeaDiscoverySection,
    IdeaKnowledgeSection,
    IdeaOption,
    IdeaRecommendResponse,
    JudgeResult,
    PaperId,
    PaperMetadata,
)
from services.session_store import SessionStore


def make_candidate(paper_id: str) -> dict:
    paper = PaperMetadata(
        paper_id=paper_id,
        source_ids=PaperId(doi=f"10.1000/{paper_id}"),
        title=f"Paper {paper_id}",
        authors=["Tester"],
        abstract="Relevant abstract.",
        doi=f"10.1000/{paper_id}",
        source="test",
    )
    judgement = JudgeResult(
        decision="accept",
        reason="Relevant",
        llm_relevance_score=0.9,
        embedding_relevance_score=0.8,
        quality_score=0.7,
        novelty_score=0.6,
        final_score=0.75,
        tags=["test"],
    )
    return {"paper": paper.model_dump(), "judgement": judgement.model_dump()}


def make_log() -> ExperimentLogRequest:
    return ExperimentLogRequest(
        task="graph reconstruction",
        model="GNN",
        dataset="synthetic graphs",
        metric_problem="edge recall is low",
        tried_methods=["message passing"],
        observation="thin edges are missed",
        goal="improve edge recall",
        tags=["graphs"],
    )


class FakeDiscoveryGraph:
    def __init__(self, candidates=None, error=None):
        self.candidates = candidates or []
        self.error = error
        self.received = None

    def invoke(self, state):
        self.received = state
        if self.error is not None:
            raise self.error
        return {
            **state,
            "rewritten_queries": ["graph topology reconstruction"],
            "raw_results": [1, 2, 3],
            "deduped_papers": [1, 2],
            "judge_failures": ["paper-broken: judge offline"],
            "ranked_candidates": self.candidates,
        }


@pytest.fixture
def candidate_service(tmp_path):
    database_path = tmp_path / "memory.sqlite3"
    store = MemoryStore(str(database_path))
    store.initialize()
    sessions = SessionStore(str(database_path))
    service = CandidateLifecycleService(str(database_path))

    store.save_candidate_paper(
        PaperMetadata(**make_candidate("saved-paper")["paper"]),
        JudgeResult(**make_candidate("saved-paper")["judgement"]),
    )
    store.update_paper_status("saved-paper", "accepted")

    first = sessions.start_turn("default", "request-1", {"text": "first"})
    service.create_batch(
        "default", first.turn_id, "old query", [make_candidate("expired-paper")]
    )
    sessions.complete_turn(first.turn_id, {"text": "done"}, {"plan_type": "research"})
    second = sessions.start_turn("default", "request-2", {"text": "second"})
    return service, second.turn_id


def test_research_agent_filters_saved_and_recent_expired_candidates(candidate_service):
    service, turn_id = candidate_service
    graph = FakeDiscoveryGraph(
        [
            make_candidate("saved-paper"),
            make_candidate("expired-paper"),
            make_candidate("fresh-paper"),
        ]
    )
    agent = ResearchAgent(graph, service)

    result = agent.run(
        session_id="default",
        turn_id=turn_id,
        query="graph reconstruction",
        memory_context="session research context",
        top_k=5,
    )

    assert [item["paper"]["paper_id"] for item in result.research.top_k] == [
        "fresh-paper"
    ]
    assert result.research.requested_top_k == 5
    assert result.research.returned_count == 1
    assert result.research.batch_id is not None
    assert graph.received["memory_context_is_snapshot"] is True
    assert result.errors[0].stage == "llm_judge"


def test_research_agent_returns_typed_discovery_failure_without_creating_batch(
    candidate_service,
):
    service, turn_id = candidate_service
    agent = ResearchAgent(
        FakeDiscoveryGraph(
            error=DiscoveryStageError("multi_search", "provider offline", True)
        ),
        service,
    )

    result = agent.run("default", turn_id, "graph reconstruction", "context", 5)

    assert result.status == "failed"
    assert result.research.error == "provider offline"
    assert result.research.batch_id is None
    assert result.errors[0].stage == "multi_search"


def test_research_agent_does_not_hide_programming_errors(candidate_service):
    service, turn_id = candidate_service
    agent = ResearchAgent(FakeDiscoveryGraph(error=TypeError("bug")), service)

    with pytest.raises(TypeError, match="bug"):
        agent.run("default", turn_id, "graph reconstruction", "context", 5)


class FakeIdeaService:
    def __init__(self, error=None):
        self.error = error
        self.received_candidates = None
        self.include_discovery = None

    def recommend(self, **kwargs):
        self.received_candidates = kwargs["discovery_candidates"]
        self.include_discovery = kwargs["include_discovery"]
        if self.error is not None:
            raise self.error
        return IdeaRecommendResponse(
            log_id=7,
            query="graph reconstruction",
            knowledge=IdeaKnowledgeSection(),
            discovery=IdeaDiscoverySection(
                enabled=False, candidates=list(self.received_candidates)
            ),
            ideas=[
                IdeaOption(
                    title="Preserve thin edges",
                    rationale="Use supplied research evidence.",
                    expected_benefit="Higher recall",
                    risk="More false positives",
                    suggested_validation_metric="edge recall",
                    next_small_experiment="Run one ablation.",
                )
            ],
            mode="deterministic",
        )


def test_idea_agent_uses_research_evidence_without_running_discovery():
    service = FakeIdeaService()
    agent = IdeaAgent(service)
    research_candidates = [make_candidate("fresh-paper")]

    result = agent.run(
        experiment_log=make_log(),
        research_candidates=research_candidates,
        idea_count=3,
    )

    assert service.received_candidates == research_candidates
    assert service.include_discovery is False
    assert result.idea.enabled is True
    assert result.status == "completed"


def test_idea_agent_returns_typed_service_failure():
    agent = IdeaAgent(FakeIdeaService(error=IdeaServiceError("generation failed", 503)))

    result = agent.run(make_log(), [], 3)

    assert result.status == "failed"
    assert result.idea.error == "generation failed"
    assert result.errors[0].stage == "idea_generation"
