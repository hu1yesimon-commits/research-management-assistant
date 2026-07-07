import sqlite3
import time

import pytest

from agent_team.contracts import AgentError, AgentResult, LeaderPlan, ResearchResult
from agent_team.dispatcher import DirectAgentDispatcher, TurnDeadlineExceeded
from agent_team.idea_agent import IdeaAgent
from agent_team.research_agent import ResearchAgent
from graph.errors import DiscoveryStageError
from services.candidate_lifecycle import CandidateLifecycleService
from services.idea_service import IdeaServiceError
from services.memory_store import MemoryStore
from services.qa_service import QAServiceError
from services.schemas import (
    ExperimentLogRequest,
    IdeaDiscoverySection,
    IdeaKnowledgeSection,
    IdeaOption,
    IdeaRecommendResponse,
    IdeaResult,
    JudgeResult,
    KnowledgeAnswerResponse,
    PaperId,
    PaperMetadata,
)
from services.session_store import SessionStore
from services.session_schemas import SessionContext


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


class StubResearchAgent:
    def __init__(self, result=None, error=None, delay=0):
        self.result = result
        self.error = error
        self.delay = delay

    def run(self, **kwargs):
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result or AgentResult(
            agent_name="research",
            action="recommend_papers",
            status="completed",
            research=ResearchResult(
                requested_top_k=kwargs["top_k"],
                returned_count=1,
                top_k=[make_candidate("fresh-paper")],
            ),
        )


class StubIdeaAgent:
    def __init__(self):
        self.received_candidates = None
        self.call_count = 0

    def run(self, **kwargs):
        self.call_count += 1
        self.received_candidates = kwargs["research_candidates"]
        return AgentResult(
            agent_name="idea", action="generate_ideas", status="completed",
            idea=IdeaResult(
                enabled=True,
                ideas=[
                    IdeaOption(
                        title="Preserve thin edges",
                        rationale="Use evidence.",
                        expected_benefit="Higher recall",
                        risk="False positives",
                        suggested_validation_metric="edge recall",
                        next_small_experiment="Run an ablation.",
                    )
                ],
            ),
        )


@pytest.fixture
def dispatch_store(tmp_path):
    path = tmp_path / "dispatcher.sqlite3"
    MemoryStore(str(path)).initialize()
    store = SessionStore(str(path))
    turn = store.start_turn("default", "dispatcher-request", {"text": "help"})
    return store, turn.turn_id


def make_context():
    return SessionContext(
        session_id="default",
        agent_contexts={"research": "prior research context"},
    )


def research_then_idea_plan():
    return LeaderPlan(
        goal="research and ideate",
        plan_type="research_then_idea",
        steps=[
            {"id": "research-1", "agent": "research", "action": "recommend_papers",
             "input": {"query": "graph reconstruction", "top_k": 5}},
            {"id": "idea-1", "agent": "idea", "action": "generate_ideas",
             "input": {"idea_count": 3}, "depends_on": ["research-1"]},
        ],
    )


def make_dispatcher(store, research_agent):
    return DirectAgentDispatcher(
        knowledge_service=None,
        research_agent=research_agent,
        idea_agent=StubIdeaAgent(),
        session_store=store,
        agent_step_timeout_seconds=0.05,
    )


class StubKnowledgeService:
    def __init__(self, error=None):
        self.error = error
        self.received = None

    def answer(self, **kwargs):
        self.received = kwargs
        if self.error is not None:
            raise self.error
        return KnowledgeAnswerResponse(
            question=kwargs["question"],
            answer="Grounded answer",
            sources=[],
            mode="deterministic",
        )


def knowledge_plan():
    return LeaderPlan(
        goal="answer from knowledge",
        plan_type="knowledge_qa",
        steps=[
            {
                "id": "knowledge-1",
                "agent": "knowledge",
                "action": "answer",
                "input": {"question": "What preserves thin edges?", "top_k": 4},
            }
        ],
    )


def test_research_then_idea_passes_research_output_to_idea(dispatch_store):
    store, turn_id = dispatch_store
    dispatcher = make_dispatcher(store, StubResearchAgent())

    results = dispatcher.execute(
        "default", turn_id, research_then_idea_plan(), make_log(), make_context()
    )

    assert [result.agent_name for result in results] == ["research", "idea"]
    assert dispatcher.idea_agent.received_candidates == results[0].research.top_k
    assert store.get_agent_context("default", "research").startswith(
        "query=graph reconstruction; returned=1"
    )
    assert store.get_agent_context("default", "idea").startswith(
        "experiment=graph reconstruction; ideas=Preserve thin edges"
    )


def test_failed_dependency_marks_idea_skipped_and_persists_terminal_runs(dispatch_store):
    store, turn_id = dispatch_store
    failed = AgentResult(
        agent_name="research", action="recommend_papers", status="failed",
        research=ResearchResult(requested_top_k=5, returned_count=0, error="offline"),
        errors=[AgentError(agent_name="research", stage="search", message="offline")],
    )
    dispatcher = make_dispatcher(store, StubResearchAgent(result=failed))

    results = dispatcher.execute(
        "default", turn_id, research_then_idea_plan(), make_log(), make_context()
    )

    assert [result.status for result in results] == ["failed", "skipped"]
    with sqlite3.connect(store.database_path) as connection:
        rows = connection.execute(
            "SELECT status FROM agent_runs ORDER BY started_at, rowid"
        ).fetchall()
    assert [row[0] for row in rows] == ["failed", "skipped"]


def test_agent_step_timeout_becomes_typed_failure(dispatch_store):
    store, turn_id = dispatch_store
    dispatcher = make_dispatcher(store, StubResearchAgent(delay=0.2))
    plan = LeaderPlan(
        goal="research", plan_type="research",
        steps=[{"id": "research-1", "agent": "research",
                "action": "recommend_papers", "input": {"query": "graphs"}}],
    )

    results = dispatcher.execute("default", turn_id, plan, None, make_context())

    assert results[0].status == "failed"
    assert results[0].errors[0].stage == "timeout"


def test_timeout_dependency_marks_idea_skipped(dispatch_store):
    store, turn_id = dispatch_store
    dispatcher = make_dispatcher(store, StubResearchAgent(delay=0.2))

    results = dispatcher.execute(
        "default", turn_id, research_then_idea_plan(), make_log(), make_context()
    )

    assert [result.status for result in results] == ["failed", "skipped"]
    assert results[0].errors[0].stage == "timeout"
    assert results[1].errors[0].stage == "dependency"


def test_typed_knowledge_failure_is_recoverable_and_persisted(dispatch_store):
    store, turn_id = dispatch_store
    dispatcher = DirectAgentDispatcher(
        knowledge_service=StubKnowledgeService(
            error=QAServiceError("retrieval unavailable", status_code=503)
        ),
        research_agent=None,
        idea_agent=None,
        session_store=store,
        agent_step_timeout_seconds=0.05,
    )

    results = dispatcher.execute(
        "default", turn_id, knowledge_plan(), None, make_context()
    )

    assert results[0].status == "failed"
    assert results[0].errors == [
        AgentError(
            agent_name="knowledge",
            stage="knowledge_answer",
            message="retrieval unavailable",
            recoverable=True,
        )
    ]
    with sqlite3.connect(store.database_path) as connection:
        status, error_json = connection.execute(
            "SELECT status, error_json FROM agent_runs"
        ).fetchone()
    assert status == "failed"
    assert "retrieval unavailable" in error_json


def test_knowledge_dispatch_reuses_prefetched_results(dispatch_store):
    store, turn_id = dispatch_store
    knowledge_service = StubKnowledgeService()
    dispatcher = DirectAgentDispatcher(
        knowledge_service=knowledge_service,
        research_agent=None,
        idea_agent=None,
        session_store=store,
        agent_step_timeout_seconds=0.05,
    )
    context = make_context().model_copy(update={"current_knowledge": []})

    result = dispatcher.execute(
        "default", turn_id, knowledge_plan(), None, context
    )[0]

    assert result.status == "completed"
    assert knowledge_service.received["retrieved_results"] is context.current_knowledge


def test_unexpected_exception_persists_failed_then_reraises(dispatch_store):
    store, turn_id = dispatch_store
    dispatcher = make_dispatcher(store, StubResearchAgent(error=TypeError("bug")))
    plan = LeaderPlan(
        goal="research", plan_type="research",
        steps=[{"id": "research-1", "agent": "research",
                "action": "recommend_papers", "input": {"query": "graphs"}}],
    )

    with pytest.raises(TypeError, match="bug"):
        dispatcher.execute("default", turn_id, plan, None, make_context())

    with sqlite3.connect(store.database_path) as connection:
        row = connection.execute(
            "SELECT status, error_json FROM agent_runs"
        ).fetchone()
    assert row[0] == "failed"
    assert "bug" in row[1]


def test_turn_deadline_expiry_between_steps_never_starts_idea(dispatch_store):
    store, turn_id = dispatch_store
    dispatcher = make_dispatcher(store, StubResearchAgent())
    remaining = iter((1.0, 0.0))

    with pytest.raises(TurnDeadlineExceeded):
        dispatcher.execute(
            "default",
            turn_id,
            research_then_idea_plan(),
            make_log(),
            make_context(),
            remaining_turn_seconds=lambda: next(remaining),
        )

    assert dispatcher.idea_agent.call_count == 0
    with sqlite3.connect(store.database_path) as connection:
        rows = connection.execute(
            "SELECT agent_name, status FROM agent_runs ORDER BY started_at, rowid"
        ).fetchall()
    assert rows == [("research", "completed")]


def test_turn_budget_caps_agent_step_timeout_and_persists_failure(dispatch_store):
    store, turn_id = dispatch_store
    dispatcher = make_dispatcher(store, StubResearchAgent(delay=0.2))
    plan = LeaderPlan(
        goal="research",
        plan_type="research",
        steps=[
            {
                "id": "research-1",
                "agent": "research",
                "action": "recommend_papers",
                "input": {"query": "graphs"},
            }
        ],
    )

    with pytest.raises(TurnDeadlineExceeded):
        dispatcher.execute(
            "default",
            turn_id,
            plan,
            None,
            make_context(),
            remaining_turn_seconds=lambda: 0.01,
        )

    with sqlite3.connect(store.database_path) as connection:
        status, error_json = connection.execute(
            "SELECT status, error_json FROM agent_runs"
        ).fetchone()
    assert status == "failed"
    assert "0.01 seconds" in error_json
