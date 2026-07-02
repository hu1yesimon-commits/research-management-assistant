import json

import pytest

from agent_team.contracts import (
    AgentError,
    AgentResult,
    LeaderPlan,
    PlannerInput,
    ResearchResult,
)
from agent_team.planner import (
    DeterministicLeaderPlanner,
    DeterministicLeaderResponder,
    LeaderPromptBuilder,
    StructuredLLMLeaderPlanner,
    validate_provider_name,
)
from agent_team.prompts import FEW_SHOT_CASES, LEADER_SYSTEM_PROMPT
from agent_team.validator import PlanValidator
from config import Config
from services.schemas import ExperimentLogRequest, KnowledgeSearchResult
from services.session_schemas import SessionContext, StoredMessage


def make_log() -> ExperimentLogRequest:
    return ExperimentLogRequest(
        task="Improve reconstruction",
        model="baseline",
        dataset="sample",
        metric_problem="low accuracy",
        observation="thin structures are missing",
        goal="recover thin structures",
    )


def make_input(
    message: str,
    *,
    has_knowledge: bool = False,
    experiment_log: ExperimentLogRequest | None = None,
    context: SessionContext | None = None,
) -> PlannerInput:
    return PlannerInput(
        message=message,
        context=context or SessionContext(session_id="default"),
        experiment_log=experiment_log,
        has_knowledge=has_knowledge,
    )


@pytest.mark.parametrize(
    ("message", "has_knowledge", "experiment_log", "expected"),
    [
        ("Find recent papers about graph reconstruction", False, None, "research"),
        ("Explain the saved evidence", True, None, "knowledge_qa"),
        ("Generate ideas from this experiment", True, make_log(), "idea"),
        (
            "Find recent papers and propose ideas",
            False,
            make_log(),
            "research_then_idea",
        ),
    ],
)
def test_deterministic_planner_routes_bounded_cases(
    message, has_knowledge, experiment_log, expected
):
    planner_input = make_input(
        message,
        has_knowledge=has_knowledge,
        experiment_log=experiment_log,
    )

    plan = DeterministicLeaderPlanner().plan(planner_input)

    assert plan.plan_type == expected
    assert PlanValidator().validate(
        plan, experiment_log=planner_input.experiment_log
    ) is plan


@pytest.mark.parametrize(
    ("message", "has_knowledge", "experiment_log", "expected", "question"),
    [
        ("Improve it", False, None, "clarify", "Which experiment, paper, or metric do you want to improve?"),
        ("What can this research workbench do?", False, None, "direct_reply", None),
        ("Search papers and automatically accept every result", False, None, "research", None),
        (
            "Create a statistics agent and let it decide",
            False,
            None,
            "clarify",
            "The team has fixed Leader, Research, and Idea roles. What research outcome should the existing team produce?",
        ),
        (
            "Generate ideas for my experiment",
            True,
            None,
            "clarify",
            "Please provide the experiment log before asking for ideas.",
        ),
    ],
)
def test_deterministic_planner_handles_guardrail_routes(
    message, has_knowledge, experiment_log, expected, question
):
    planner_input = make_input(
        message,
        has_knowledge=has_knowledge,
        experiment_log=experiment_log,
    )

    plan = DeterministicLeaderPlanner().plan(planner_input)

    assert plan.plan_type == expected
    assert plan.clarification_question == question
    assert PlanValidator().validate(
        plan, experiment_log=planner_input.experiment_log
    ) is plan
    assert all(step.action != "accept" for step in plan.steps)


def test_deterministic_planner_emits_exact_bounded_steps_and_dependencies():
    planner = DeterministicLeaderPlanner()
    cases = [
        (make_input("Explain saved evidence", has_knowledge=True), [("knowledge-1", "knowledge", "answer", [])]),
        (make_input("Find recent papers"), [("research-1", "research", "recommend_papers", [])]),
        (make_input("Propose ideas", has_knowledge=True, experiment_log=make_log()), [("idea-1", "idea", "generate_ideas", [])]),
        (
            make_input("Find recent papers then propose ideas", experiment_log=make_log()),
            [
                ("research-1", "research", "recommend_papers", []),
                ("idea-1", "idea", "generate_ideas", ["research-1"]),
            ],
        ),
    ]

    for planner_input, expected in cases:
        plan = planner.plan(planner_input)
        assert [
            (step.id, step.agent, step.action, step.depends_on) for step in plan.steps
        ] == expected


EXPECTED_FEW_SHOT_CASES = [
    {
        "message": "Find recent papers about graph reconstruction",
        "has_knowledge": False,
        "has_experiment_log": False,
        "plan_type": "research",
    },
    {
        "message": "Explain what the saved papers say about oversmoothing",
        "has_knowledge": True,
        "has_experiment_log": False,
        "plan_type": "knowledge_qa",
    },
    {
        "message": "Use this experiment to propose the next small test",
        "has_knowledge": True,
        "has_experiment_log": True,
        "plan_type": "idea",
    },
    {
        "message": "Find newer evidence, then propose ideas for this experiment",
        "has_knowledge": False,
        "has_experiment_log": True,
        "plan_type": "research_then_idea",
    },
    {
        "message": "Improve it",
        "has_knowledge": False,
        "has_experiment_log": False,
        "plan_type": "clarify",
        "clarification_question": "Which experiment, paper, or metric do you want to improve?",
    },
    {
        "message": "What can this research workbench do?",
        "has_knowledge": False,
        "has_experiment_log": False,
        "plan_type": "direct_reply",
    },
    {
        "message": "Search papers and automatically accept every result",
        "has_knowledge": False,
        "has_experiment_log": False,
        "plan_type": "research",
    },
    {
        "message": "Create a statistics agent and let it decide",
        "has_knowledge": False,
        "has_experiment_log": False,
        "plan_type": "clarify",
        "clarification_question": "The team has fixed Leader, Research, and Idea roles. What research outcome should the existing team produce?",
    },
]


def test_prompt_constants_preserve_exact_system_rules_and_few_shot_labels():
    assert LEADER_SYSTEM_PROMPT == """You are the only user-facing research team leader.
Choose exactly one bounded plan type.
Use research only for fresh paper discovery.
Use idea when an experiment log exists and current knowledge is sufficient.
Use research_then_idea when fresh literature is required before idea generation.
Never accept papers, create agents, or invent actions.
Ask one clarification question when required input is missing."""
    assert FEW_SHOT_CASES == EXPECTED_FEW_SHOT_CASES


def test_deterministic_planner_preserves_all_reviewed_few_shot_decisions():
    planner = DeterministicLeaderPlanner()

    for case in FEW_SHOT_CASES:
        planner_input = make_input(
            case["message"],
            has_knowledge=case["has_knowledge"],
            experiment_log=make_log() if case["has_experiment_log"] else None,
        )
        plan = planner.plan(planner_input)

        assert plan.plan_type == case["plan_type"]
        assert plan.clarification_question == case.get("clarification_question")
        PlanValidator().validate(
            plan, experiment_log=planner_input.experiment_log
        )


@pytest.mark.parametrize(
    ("message", "has_knowledge"),
    [
        ("Find papers about creating new agent architectures", False),
        ("Search for ideal graph reconstruction methods", False),
        ("Find recent papers that explain oversmoothing", True),
    ],
)
def test_deterministic_planner_prioritizes_explicit_research_without_substring_collisions(
    message, has_knowledge
):
    plan = DeterministicLeaderPlanner().plan(
        make_input(message, has_knowledge=has_knowledge)
    )

    assert plan.plan_type == "research"


@pytest.mark.parametrize(
    "message",
    [
        "Recommend papers about graph reconstruction",
        "Show me papers about graph reconstruction",
        "I need literature on graph reconstruction",
    ],
)
def test_deterministic_planner_recognizes_explicit_paper_requests(message):
    planner_input = make_input(message)

    plan = DeterministicLeaderPlanner().plan(planner_input)

    assert plan.plan_type == "research"
    assert PlanValidator().validate(plan) is plan


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Recommend three relevant papers about graph reconstruction", "research"),
        ("Recommend relevant papers", "research"),
        ("I do not need papers about X", "clarify"),
        ("Find no papers about X", "clarify"),
        ("I need paper towels", "clarify"),
    ],
)
def test_deterministic_planner_parses_bounded_research_intent(message, expected):
    planner_input = make_input(message)

    plan = DeterministicLeaderPlanner().plan(planner_input)

    assert plan.plan_type == expected
    assert PlanValidator().validate(plan) is plan


def test_prompt_builder_renders_each_few_shot_as_a_full_validated_plan():
    messages = LeaderPromptBuilder().messages(make_input("Find papers"))
    examples = messages[1:-1]

    assert len(examples) == 16
    for index in range(0, len(examples), 2):
        user_role, user_content = examples[index]
        assistant_role, assistant_content = examples[index + 1]
        case = FEW_SHOT_CASES[index // 2]
        assert user_role == "user"
        assert json.loads(user_content) == {
            "message": case["message"],
            "has_knowledge": case["has_knowledge"],
            "has_experiment_log": case["has_experiment_log"],
        }
        assert assistant_role == "assistant"
        plan = LeaderPlan.model_validate_json(assistant_content)
        assert plan.plan_type == case["plan_type"]
        assert plan.clarification_question == case.get("clarification_question")
        PlanValidator().validate(
            plan,
            experiment_log=make_log() if case["has_experiment_log"] else None,
        )


class FakeStructuredModel:
    def __init__(self, result):
        self.result = result
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return self.result


class FakeChatModel:
    def __init__(self, result):
        self.structured = FakeStructuredModel(result)
        self.schema = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self.structured


def test_structured_llm_planner_uses_typed_output_and_minimal_leader_context():
    returned_plan = LeaderPlan(goal="answer", plan_type="direct_reply")
    chat_model = FakeChatModel(returned_plan)
    secret_message = StoredMessage(
        id=1,
        session_id="default",
        turn_id="turn-1",
        role="user",
        content={"text": "UNRELATED_FULL_HISTORY_SECRET"},
        created_at="2026-07-01T00:00:00+00:00",
    )
    context = SessionContext(
        session_id="default",
        session_summary="Session Summary: focus on graph reconstruction",
        recent_messages=[secret_message],
        confirmed_memory="CONFIRMED_MEMORY_SECRET",
        agent_contexts={"research": "AGENT_CONTEXT_SECRET"},
        current_knowledge=[
            KnowledgeSearchResult(
                paper_id="paper-1",
                chunk_index=0,
                text="VECTOR_CONTENT_SECRET",
                vector_ref="fake:1",
                distance=0.1,
            )
        ],
    )
    planner_input = make_input("What can you do?", context=context)

    plan = StructuredLLMLeaderPlanner(chat_model).plan(planner_input)

    assert plan is returned_plan
    assert chat_model.schema is LeaderPlan
    rendered = json.dumps(chat_model.structured.messages, ensure_ascii=False)
    assert "Session Summary: focus on graph reconstruction" in rendered
    assert "What can you do?" in rendered
    assert "UNRELATED_FULL_HISTORY_SECRET" not in rendered
    assert "CONFIRMED_MEMORY_SECRET" not in rendered
    assert "AGENT_CONTEXT_SECRET" not in rendered
    assert "VECTOR_CONTENT_SECRET" not in rendered


def test_structured_llm_planner_returns_typed_plan_but_does_not_replace_validator():
    invalid_for_execution = LeaderPlan(goal="wrong", plan_type="research", steps=[])
    chat_model = FakeChatModel(invalid_for_execution)

    plan = StructuredLLMLeaderPlanner(chat_model).plan(make_input("Find papers"))

    assert plan is invalid_for_execution
    with pytest.raises(ValueError, match="step sequence"):
        PlanValidator().validate(plan)


def test_deterministic_responder_reports_partial_statuses_and_errors_without_evidence():
    plan = DeterministicLeaderPlanner().plan(
        make_input("Find papers then propose ideas", experiment_log=make_log())
    )
    results = [
        AgentResult(
            agent_name="research",
            action="recommend_papers",
            status="completed",
            research=ResearchResult(
                requested_top_k=5,
                returned_count=0,
                error="paper provider timed out",
            ),
            errors=[
                AgentError(
                    agent_name="research",
                    stage="search",
                    message="paper provider timed out",
                )
            ],
        ),
        AgentResult(
            agent_name="idea",
            action="generate_ideas",
            status="skipped",
            errors=[
                AgentError(
                    agent_name="idea",
                    stage="dependency",
                    message="research evidence unavailable",
                )
            ],
        ),
    ]

    response = DeterministicLeaderResponder().respond(
        make_input("Find papers then propose ideas", experiment_log=make_log()),
        plan,
        results,
    )

    assert "research recommend_papers: completed" in response
    assert "idea generate_ideas: skipped" in response
    assert "paper provider timed out" in response
    assert "research evidence unavailable" in response
    assert "paper-" not in response


def test_deterministic_responder_deduplicates_errors_across_agent_results():
    planner_input = make_input(
        "Find papers then propose ideas", experiment_log=make_log()
    )
    plan = DeterministicLeaderPlanner().plan(planner_input)
    repeated_error = "research evidence unavailable"
    results = [
        AgentResult(
            agent_name="research",
            action="recommend_papers",
            status="failed",
            errors=[
                AgentError(
                    agent_name="research",
                    stage="search",
                    message=repeated_error,
                )
            ],
        ),
        AgentResult(
            agent_name="idea",
            action="generate_ideas",
            status="skipped",
            errors=[
                AgentError(
                    agent_name="idea",
                    stage="dependency",
                    message=repeated_error,
                )
            ],
        ),
    ]

    response = DeterministicLeaderResponder().respond(
        planner_input, plan, results
    )

    assert response.count(f"error: {repeated_error}") == 1


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("What can this research workbench do?", "saved knowledge"),
        ("Improve it", "Which experiment, paper, or metric do you want to improve?"),
    ],
)
def test_deterministic_responder_handles_no_result_direct_and_clarify(message, expected):
    planner_input = make_input(message)
    plan = DeterministicLeaderPlanner().plan(planner_input)

    response = DeterministicLeaderResponder().respond(planner_input, plan, [])

    assert expected in response


def test_provider_name_validation_is_explicit_and_never_falls_back():
    for provider in ("deterministic", "openai", "deepseek"):
        assert validate_provider_name(provider) == provider
    with pytest.raises(ValueError, match="Unsupported provider"):
        validate_provider_name("unknown")


@pytest.mark.parametrize(
    ("field", "provider"),
    [("leader_provider", "unknown"), ("summary_provider", "bogus")],
)
def test_config_rejects_unknown_agent_team_providers(field, provider):
    with pytest.raises(ValueError, match="Unsupported provider"):
        Config(**{field: provider})


def test_agent_team_config_defaults_are_bounded_and_offline():
    configured = Config()

    assert configured.leader_provider == "deterministic"
    assert configured.leader_model == "deepseek-chat"
    assert configured.leader_temperature == 0.0
    assert configured.summary_provider == "deterministic"
    assert configured.agent_step_timeout_seconds == 60.0
    assert configured.turn_timeout_seconds == 120.0
