import json

import pytest

from agent_team.contracts import (
    AgentError,
    AgentResult,
    LeaderPlan,
    PlannerInput,
    ResearchResult,
)
from agent_team import providers
from agent_team.providers import validate_provider_name
from agent_team.planner import (
    DeterministicLeaderPlanner,
    DeterministicLeaderResponder,
    LeaderPromptBuilder,
    StructuredLLMLeaderPlanner,
)
from agent_team.prompts import FEW_SHOT_CASES, LEADER_SYSTEM_PROMPT
from agent_team.validator import PlanValidator
from config import Config
from services.schemas import (
    ExperimentLogRequest,
    IdeaOption,
    IdeaResult,
    KnowledgeResult,
    KnowledgeSearchResult,
)
from services.session_context import (
    DeterministicSummaryGenerator,
    LLMSummaryGenerator,
)
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


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("What can you do?", "direct_reply"),
        ("What can you do? Find recent papers", "research"),
        (
            "What can you do? Do not search literature; find recent papers",
            "clarify",
        ),
        ("What can you do? Do not search papers", "direct_reply"),
    ],
)
def test_deterministic_planner_prioritizes_research_guard_over_product_reply(
    message, expected
):
    plan = DeterministicLeaderPlanner().plan(make_input(message))

    assert plan.plan_type == expected
    if expected in {"direct_reply", "clarify"}:
        assert plan.steps == []
    assert PlanValidator().validate(plan) is plan


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


def test_deterministic_planner_preserves_user_request_in_professional_step_inputs():
    planner = DeterministicLeaderPlanner()

    research = planner.plan(make_input("Find recent papers about graph reconstruction"))
    knowledge = planner.plan(make_input("Explain saved evidence", has_knowledge=True))
    research_then_idea = planner.plan(
        make_input("Find recent papers then propose ideas", experiment_log=make_log())
    )

    assert research.steps[0].input["query"] == "Find recent papers about graph reconstruction"
    assert knowledge.steps[0].input["question"] == "Explain saved evidence"
    assert research_then_idea.steps[0].input["query"] == "Find recent papers then propose ideas"


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
When current knowledge is available, prefer knowledge_qa unless the user asks for fresh search.
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
        "What does this paper say about graph reconstruction?",
        "Explain the method in the paper",
        "How does the uploaded paper solve this?",
        "Compare the saved papers",
        "Summarize the evidence we already have",
    ],
)
def test_deterministic_planner_defaults_to_knowledge_qa_when_local_knowledge_exists(
    message,
):
    plan = DeterministicLeaderPlanner().plan(
        make_input(message, has_knowledge=True)
    )

    assert plan.plan_type == "knowledge_qa"
    assert PlanValidator().validate(plan) is plan


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


@pytest.mark.parametrize(
    "message",
    [
        "Do not search literature; find recent papers",
        "Review papers about graph reconstruction",
    ],
)
def test_deterministic_planner_clarifies_conflicting_research_signals(message):
    plan = DeterministicLeaderPlanner().plan(make_input(message))

    assert plan.plan_type == "clarify"
    assert plan.steps == []
    assert PlanValidator().validate(plan) is plan


@pytest.mark.parametrize(
    ("has_knowledge", "expected"),
    [(False, "clarify"), (True, "idea")],
)
def test_deterministic_planner_does_not_silently_research_denied_idea_requests(
    has_knowledge, expected
):
    planner_input = make_input(
        "Do not search papers; propose ideas from this experiment",
        has_knowledge=has_knowledge,
        experiment_log=make_log(),
    )

    plan = DeterministicLeaderPlanner().plan(planner_input)

    assert plan.plan_type == expected
    assert PlanValidator().validate(plan, experiment_log=make_log()) is plan


@pytest.mark.parametrize(
    ("message", "has_knowledge"),
    [
        ("Find recent papers and propose ideas from this experiment", True),
        ("Propose the next test for this experiment", False),
    ],
)
def test_deterministic_planner_preserves_required_research_before_ideas(
    message, has_knowledge
):
    planner_input = make_input(
        message,
        has_knowledge=has_knowledge,
        experiment_log=make_log(),
    )

    plan = DeterministicLeaderPlanner().plan(planner_input)

    assert plan.plan_type == "research_then_idea"
    assert PlanValidator().validate(plan, experiment_log=make_log()) is plan


@pytest.mark.parametrize(
    ("message", "has_knowledge", "expected"),
    [
        ("Review my saved papers", True, "knowledge_qa"),
        ("Review experiment logs", False, "clarify"),
    ],
)
def test_deterministic_planner_routes_existing_review_only_with_coverage(
    message, has_knowledge, expected
):
    plan = DeterministicLeaderPlanner().plan(
        make_input(message, has_knowledge=has_knowledge)
    )

    assert plan.plan_type == expected
    assert PlanValidator().validate(plan) is plan


@pytest.mark.parametrize(
    "message",
    [
        "Review recent papers",
        "Recent papers",
        "Review existing papers and find new papers",
    ],
)
def test_deterministic_planner_routes_fresh_research_signals(message):
    plan = DeterministicLeaderPlanner().plan(make_input(message))

    assert plan.plan_type == "research"
    assert PlanValidator().validate(plan) is plan


@pytest.mark.parametrize(
    ("has_knowledge", "expected"),
    [(True, "idea"), (False, "clarify")],
)
def test_deterministic_planner_keeps_existing_review_idea_routing_with_leader(
    has_knowledge, expected
):
    planner_input = make_input(
        "Review my saved papers and propose ideas from this experiment",
        has_knowledge=has_knowledge,
        experiment_log=make_log(),
    )

    plan = DeterministicLeaderPlanner().plan(planner_input)

    assert plan.plan_type == expected
    assert PlanValidator().validate(plan, experiment_log=make_log()) is plan


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

    assert "Found 0 candidate papers." in response
    assert "No fresh candidate papers were returned for this search." in response
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


def test_deterministic_responder_summarizes_successful_typed_payloads_for_chat():
    planner_input = make_input(
        "Find papers then propose ideas", experiment_log=make_log()
    )
    plan = DeterministicLeaderPlanner().plan(planner_input)
    results = [
        AgentResult(
            agent_name="knowledge",
            action="answer",
            status="completed",
            knowledge=KnowledgeResult(
                enabled=True,
                answer="Saved evidence supports residual connections.",
                mode="grounded",
            ),
        ),
        AgentResult(
            agent_name="research",
            action="recommend_papers",
            status="completed",
            research=ResearchResult(
                requested_top_k=5,
                returned_count=1,
                batch_id="batch-1",
                top_k=[
                    {
                        "paper": {
                            "paper_id": "paper-1",
                            "title": "Graph Reconstruction",
                            "abstract": "LONG_ABSTRACT_SHOULD_NOT_APPEAR",
                        }
                    }
                ],
            ),
        ),
        AgentResult(
            agent_name="idea",
            action="generate_ideas",
            status="completed",
            idea=IdeaResult(
                enabled=True,
                ideas=[
                    IdeaOption(
                        title="Add residual decoding",
                        rationale="Preserve thin structures.",
                        expected_benefit="Higher recall",
                        risk="Extra parameters",
                        suggested_validation_metric="thin-structure recall",
                        next_small_experiment="Run one seeded ablation.",
                    )
                ],
            ),
        ),
    ]

    response = DeterministicLeaderResponder().respond(planner_input, plan, results)

    assert "Saved evidence supports residual connections." in response
    assert "Found 1 candidate paper." in response
    assert "Review it in Active Candidates" in response
    assert "Graph Reconstruction" not in response
    assert "paper-1" not in response
    assert "LONG_ABSTRACT_SHOULD_NOT_APPEAR" not in response
    assert "top_k" not in response
    assert "Add residual decoding" in response
    assert "Run one seeded ablation." in response


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


class RecordingChatModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_provider_factories_keep_deterministic_defaults_offline():
    configured = Config()

    assert isinstance(
        providers.build_leader_planner(configured), DeterministicLeaderPlanner
    )
    assert isinstance(
        providers.build_summary_generator(configured), DeterministicSummaryGenerator
    )


@pytest.mark.parametrize("provider", ["openai", "deepseek"])
def test_provider_factories_construct_permitted_real_leader_and_summary(provider):
    configured = Config(
        leader_provider=provider,
        summary_provider=provider,
        leader_model="leader-test-model",
        leader_temperature=0.25,
        deepseek_api_key="test-key",
        deepseek_base_url="https://deepseek.invalid/v1",
    )

    leader = providers.build_leader_planner(
        configured, chat_model_cls=RecordingChatModel
    )
    summary = providers.build_summary_generator(
        configured, chat_model_cls=RecordingChatModel
    )

    assert isinstance(leader, StructuredLLMLeaderPlanner)
    assert isinstance(summary, LLMSummaryGenerator)
    assert leader.chat_model.kwargs["model"] == "leader-test-model"
    assert leader.chat_model.kwargs["temperature"] == 0.25
    assert summary.chat_model.kwargs == leader.chat_model.kwargs
    if provider == "deepseek":
        assert leader.chat_model.kwargs["api_key"] == "test-key"
        assert leader.chat_model.kwargs["base_url"] == "https://deepseek.invalid/v1"
    else:
        assert "api_key" not in leader.chat_model.kwargs
        assert "base_url" not in leader.chat_model.kwargs


@pytest.mark.parametrize(
    ("factory_name", "field"),
    [
        ("build_leader_planner", "leader_provider"),
        ("build_summary_generator", "summary_provider"),
    ],
)
def test_provider_factories_reject_unknown_names_at_construction(factory_name, field):
    configured = Config()
    setattr(configured, field, "unknown")

    with pytest.raises(ValueError, match="Unsupported provider"):
        getattr(providers, factory_name)(
            configured, chat_model_cls=RecordingChatModel
        )


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
    assert configured.agent_step_timeout_seconds == 120.0
    assert configured.turn_timeout_seconds == 240.0
