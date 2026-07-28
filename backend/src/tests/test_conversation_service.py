import sqlite3
from types import SimpleNamespace

import pytest

from agent_team.contracts import (
    AgentError,
    AgentResult,
    LeaderPlan,
    ResearchResult,
)
from agent_team.validator import PlanValidator
from services.candidate_lifecycle import CandidateLifecycleService
from services.conversation_service import ConversationService, TurnTimeoutError
from services.memory_store import MemoryStore
from services.retrieval_service import RetrievalServiceError
from services.schemas import IdeaOption, IdeaResult
from services.session_schemas import SessionContext, SessionTurnRequest
from services.session_store import SessionStore


class StubContextBuilder:
    def build(self, session_id):
        return SessionContext(session_id=session_id)


class StubRetrieval:
    def __init__(self, error=None):
        self.error = error

    def search(self, query, top_k):
        if self.error is not None:
            raise self.error
        return SimpleNamespace(results=[])


class StubPlanner:
    def __init__(self, plan=None, error=None):
        self.output = plan or make_plan("direct_reply")
        self.error = error
        self.call_count = 0
        self.received = None

    def plan(self, planner_input):
        self.call_count += 1
        self.received = planner_input
        if self.error is not None:
            raise self.error
        return self.output


class StubDispatcher:
    def __init__(self, results=None, on_execute=None):
        self.results = results or []
        self.on_execute = on_execute
        self.call_count = 0

    def execute(
        self,
        session_id,
        turn_id,
        plan,
        experiment_log,
        context,
        remaining_turn_seconds=None,
    ):
        self.call_count += 1
        if self.on_execute is not None:
            self.on_execute(session_id, turn_id)
        return self.results


class StubResponder:
    def __init__(self):
        self.call_count = 0

    def respond(self, planner_input, plan, results):
        self.call_count += 1
        if plan.plan_type == "clarify":
            return plan.clarification_question
        return "Leader response"


class StubSummaryService:
    def __init__(self):
        self.call_count = 0

    def maybe_refresh(self, session_id):
        self.call_count += 1
        return False


def make_plan(plan_type):
    if plan_type == "research_then_idea":
        steps = [
            {
                "id": "research-1",
                "agent": "research",
                "action": "recommend_papers",
                "input": {"query": "graphs", "top_k": 5},
            },
            {
                "id": "idea-1",
                "agent": "idea",
                "action": "generate_ideas",
                "input": {"idea_count": 3},
                "depends_on": ["research-1"],
            },
        ]
    elif plan_type == "research":
        steps = [
            {
                "id": "research-1",
                "agent": "research",
                "action": "recommend_papers",
                "input": {"query": "graphs", "top_k": 5},
            }
        ]
    else:
        steps = []
    return LeaderPlan(
        goal="test goal",
        plan_type=plan_type,
        steps=steps,
        needs_clarification=plan_type == "clarify",
        clarification_question="Please clarify." if plan_type == "clarify" else None,
    )


def make_request(message="Explain the current status", key="request-1", log=None):
    return SessionTurnRequest(
        message=message,
        idempotency_key=key,
        experiment_log=log,
    )


@pytest.fixture
def dependencies(tmp_path):
    path = tmp_path / "conversation.sqlite3"
    MemoryStore(str(path)).initialize()
    store = SessionStore(str(path))
    return {
        "store": store,
        "candidate_service": CandidateLifecycleService(str(path)),
        "context_builder": StubContextBuilder(),
        "knowledge_retrieval": StubRetrieval(),
        "planner": StubPlanner(),
        "validator": PlanValidator(),
        "dispatcher": StubDispatcher(),
        "responder": StubResponder(),
        "summary_service": StubSummaryService(),
    }


def make_service(dependencies, **overrides):
    return ConversationService(**{**dependencies, **overrides})


def seed_active_batch(store):
    first = store.start_turn("default", "seed", {"text": "seed"})
    store.complete_turn(first.turn_id, {"seed": True}, {"plan_type": "research"})
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            INSERT INTO candidate_batches (id, session_id, turn_id, query, status, created_at)
            VALUES ('old-batch', 'default', ?, 'old', 'active', '2026-01-01')
            """,
            (first.turn_id,),
        )
        connection.execute(
            """
            INSERT INTO candidate_items (
                id, batch_id, paper_key, paper_snapshot_json, status, created_at, updated_at
            ) VALUES ('old-item', 'old-batch', 'paper:old', '{}', 'active', '2026-01-01', '2026-01-01')
            """
        )


def test_new_turn_expires_old_candidates_before_planning(dependencies):
    seed_active_batch(dependencies["store"])
    service = make_service(dependencies)

    response = service.run("default", make_request())

    assert response.status == "completed"
    assert service.candidate_service.list_active("default") == []


def test_retrieval_failure_falls_back_to_empty_current_knowledge(dependencies):
    retrieval = StubRetrieval(RetrievalServiceError("offline", status_code=503))
    service = make_service(dependencies, knowledge_retrieval=retrieval)

    response = service.run("default", make_request())

    assert response.status == "completed"
    assert service.planner.received.has_knowledge is False
    assert service.planner.received.context.current_knowledge == []


def test_research_success_and_idea_failure_returns_partial_success(dependencies):
    results = [
        AgentResult(
            agent_name="research",
            action="recommend_papers",
            status="completed",
            research=ResearchResult(requested_top_k=5, returned_count=1),
        ),
        AgentResult(
            agent_name="idea",
            action="generate_ideas",
            status="failed",
            idea=IdeaResult(enabled=True, error="idea provider offline"),
            errors=[
                AgentError(
                    agent_name="idea",
                    stage="idea_generation",
                    message="idea provider offline",
                )
            ],
        ),
    ]
    planner = StubPlanner(make_plan("research_then_idea"))
    dispatcher = StubDispatcher(results)
    service = make_service(dependencies, planner=planner, dispatcher=dispatcher)
    request = make_request(log={
        "task": "graphs",
        "model": "GNN",
        "dataset": "synthetic",
        "metric_problem": "low recall",
        "tried_methods": [],
        "observation": "thin edges missed",
        "goal": "improve recall",
    })

    response = service.run("default", request)

    assert response.status == "completed"
    assert response.ideas == []
    assert response.errors[0].agent_name == "idea"
    assert [run.status for run in response.agent_runs] == ["completed", "failed"]


def test_idempotent_retry_returns_original_response(dependencies):
    service = make_service(dependencies)
    request = make_request(message="Find papers", key="same-key")

    first = service.run("default", request)
    second = service.run("default", request)

    assert first == second
    assert service.planner.call_count == 1
    assert service.summary_service.call_count == 1


def test_direct_and_clarify_plans_create_no_agent_runs(dependencies):
    for index, plan_type in enumerate(("direct_reply", "clarify"), start=1):
        planner = StubPlanner(make_plan(plan_type))
        service = make_service(dependencies, planner=planner)
        response = service.run("default", make_request(key=f"bounded-{index}"))
        assert response.status == "completed"

    with sqlite3.connect(dependencies["store"].database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0] == 0


def test_plan_validation_failure_returns_clarification_without_dispatch(dependencies):
    invalid = LeaderPlan(
        goal="invalid",
        plan_type="research",
        steps=[],
    )
    dispatcher = StubDispatcher()
    service = make_service(
        dependencies,
        planner=StubPlanner(invalid),
        dispatcher=dispatcher,
    )

    response = service.run("default", make_request())

    assert response.status == "completed"
    assert response.plan.plan_type == "clarify"
    assert dispatcher.call_count == 0


def test_turn_timeout_marks_turn_failed(dependencies):
    ticks = iter((0.0, 2.0))
    service = make_service(
        dependencies,
        turn_timeout_seconds=1.0,
        monotonic=lambda: next(ticks),
    )

    with pytest.raises(TurnTimeoutError):
        service.run("default", make_request(message="Find papers"))

    messages = dependencies["store"].list_messages("default")
    turn = dependencies["store"].get_turn("default", messages[0].turn_id)
    assert turn["status"] == "failed"
    assert turn["error"]["stage"] == "timeout"


def test_unexpected_exception_fails_turn_then_reraises(dependencies):
    service = make_service(
        dependencies,
        planner=StubPlanner(error=TypeError("planner bug")),
    )

    with pytest.raises(TypeError, match="planner bug"):
        service.run("default", make_request())

    turn_id = dependencies["store"].list_messages("default")[0].turn_id
    turn = dependencies["store"].get_turn("default", turn_id)
    assert turn["status"] == "failed"
    assert turn["error"]["type"] == "TypeError"


def test_summary_runs_only_after_turn_completion(dependencies):
    observed = []

    class ObservingSummary:
        def maybe_refresh(self, session_id):
            turn_id = dependencies["store"].list_messages(session_id)[-1].turn_id
            observed.append(dependencies["store"].get_turn(session_id, turn_id)["status"])

    service = make_service(dependencies, summary_service=ObservingSummary())

    service.run("default", make_request())

    assert observed == ["completed"]


def test_summary_failure_is_nonfatal_and_replay_remains_completed(dependencies):
    class FailingSummary:
        def maybe_refresh(self, session_id):
            raise RuntimeError("summary unavailable")

    service = make_service(dependencies, summary_service=FailingSummary())
    request = make_request(key="summary-failure")

    first = service.run("default", request)
    replay = service.run("default", request)

    assert first == replay
    assert first.status == "completed"
    turn = dependencies["store"].get_turn("default", first.turn_id)
    assert turn["status"] == "completed"
