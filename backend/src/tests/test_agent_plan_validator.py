import pytest
from pydantic import ValidationError

from agent_team.contracts import LeaderPlan, PlanStep, PlannerInput
from agent_team.validator import PlanValidationError, validate_plan
from services.schemas import ExperimentLogRequest
from services.session_schemas import SessionContext


def _experiment_log() -> ExperimentLogRequest:
    return ExperimentLogRequest(
        task="Improve reconstruction",
        model="baseline",
        dataset="sample",
        metric_problem="low accuracy",
        observation="thin structures are missing",
        goal="recover thin structures",
    )


def _planner_input(*, with_experiment_log: bool = False) -> PlannerInput:
    return PlannerInput(
        message="Help with the experiment",
        context=SessionContext(session_id="session-1"),
        experiment_log=_experiment_log() if with_experiment_log else None,
    )


@pytest.mark.parametrize(
    ("plan", "with_experiment_log"),
    [
        (LeaderPlan(goal="reply", plan_type="direct_reply"), False),
        (
            LeaderPlan(
                goal="answer",
                plan_type="knowledge_qa",
                steps=[PlanStep(id="knowledge-1", agent="knowledge", action="answer")],
            ),
            False,
        ),
        (
            LeaderPlan(
                goal="research",
                plan_type="research",
                steps=[
                    PlanStep(
                        id="research-1",
                        agent="research",
                        action="recommend_papers",
                    )
                ],
            ),
            False,
        ),
        (
            LeaderPlan(
                goal="ideas",
                plan_type="idea",
                steps=[PlanStep(id="idea-1", agent="idea", action="generate_ideas")],
            ),
            True,
        ),
        (
            LeaderPlan(
                goal="research then ideas",
                plan_type="research_then_idea",
                steps=[
                    PlanStep(
                        id="research-1",
                        agent="research",
                        action="recommend_papers",
                    ),
                    PlanStep(
                        id="idea-1",
                        agent="idea",
                        action="generate_ideas",
                        depends_on=["research-1"],
                    ),
                ],
            ),
            True,
        ),
        (
            LeaderPlan(
                goal="clarify",
                plan_type="clarify",
                needs_clarification=True,
                clarification_question="Which dataset should I use?",
            ),
            False,
        ),
    ],
)
def test_validate_plan_accepts_each_bounded_plan_type(plan, with_experiment_log):
    assert validate_plan(plan, _planner_input(with_experiment_log=with_experiment_log)) is plan


@pytest.mark.parametrize(
    "plan",
    [
        LeaderPlan(goal="wrong count", plan_type="research", steps=[]),
        LeaderPlan(
            goal="wrong sequence",
            plan_type="knowledge_qa",
            steps=[PlanStep(id="research-1", agent="research", action="recommend_papers")],
        ),
        LeaderPlan(
            goal="wrong order",
            plan_type="research_then_idea",
            steps=[
                PlanStep(id="idea-1", agent="idea", action="generate_ideas"),
                PlanStep(id="research-1", agent="research", action="recommend_papers"),
            ],
        ),
    ],
)
def test_validate_plan_rejects_step_count_or_sequence_mismatch(plan):
    with pytest.raises(PlanValidationError, match="sequence"):
        validate_plan(plan, _planner_input(with_experiment_log=True))


def test_plan_schema_rejects_unknown_action():
    with pytest.raises(ValidationError):
        PlanStep(id="unknown-1", agent="knowledge", action="unknown")


@pytest.mark.parametrize("plan_type", ["idea", "research_then_idea"])
def test_validate_plan_requires_experiment_log_for_idea_plans(plan_type):
    steps = [PlanStep(id="idea-1", agent="idea", action="generate_ideas")]
    if plan_type == "research_then_idea":
        steps = [
            PlanStep(id="research-1", agent="research", action="recommend_papers"),
            PlanStep(
                id="idea-1",
                agent="idea",
                action="generate_ideas",
                depends_on=["research-1"],
            ),
        ]

    with pytest.raises(PlanValidationError, match="experiment_log"):
        validate_plan(LeaderPlan(goal="ideas", plan_type=plan_type, steps=steps), _planner_input())


def test_validate_plan_rejects_duplicate_step_ids():
    plan = LeaderPlan(
        goal="duplicate ids",
        plan_type="research_then_idea",
        steps=[
            PlanStep(id="step-1", agent="research", action="recommend_papers"),
            PlanStep(
                id="step-1",
                agent="idea",
                action="generate_ideas",
                depends_on=["step-1"],
            ),
        ],
    )

    with pytest.raises(PlanValidationError, match="unique"):
        validate_plan(plan, _planner_input(with_experiment_log=True))


@pytest.mark.parametrize(
    "plan",
    [
        LeaderPlan(
            goal="single dependency",
            plan_type="research",
            steps=[
                PlanStep(
                    id="research-1",
                    agent="research",
                    action="recommend_papers",
                    depends_on=["research-1"],
                )
            ],
        ),
        LeaderPlan(
            goal="first step dependency",
            plan_type="research_then_idea",
            steps=[
                PlanStep(
                    id="research-1",
                    agent="research",
                    action="recommend_papers",
                    depends_on=["idea-1"],
                ),
                PlanStep(
                    id="idea-1",
                    agent="idea",
                    action="generate_ideas",
                    depends_on=["research-1"],
                ),
            ],
        ),
        LeaderPlan(
            goal="missing dependency",
            plan_type="research_then_idea",
            steps=[
                PlanStep(id="research-1", agent="research", action="recommend_papers"),
                PlanStep(id="idea-1", agent="idea", action="generate_ideas"),
            ],
        ),
        LeaderPlan(
            goal="extra dependency",
            plan_type="research_then_idea",
            steps=[
                PlanStep(id="research-1", agent="research", action="recommend_papers"),
                PlanStep(
                    id="idea-1",
                    agent="idea",
                    action="generate_ideas",
                    depends_on=["research-1", "idea-1"],
                ),
            ],
        ),
    ],
)
def test_validate_plan_rejects_forbidden_dependencies_and_loop_shapes(plan):
    with pytest.raises(PlanValidationError, match="depends_on"):
        validate_plan(plan, _planner_input(with_experiment_log=True))


@pytest.mark.parametrize(
    "plan",
    [
        LeaderPlan(goal="missing flag", plan_type="clarify", clarification_question="Which dataset?"),
        LeaderPlan(goal="missing question", plan_type="clarify", needs_clarification=True),
        LeaderPlan(
            goal="blank question",
            plan_type="clarify",
            needs_clarification=True,
            clarification_question="   ",
        ),
    ],
)
def test_validate_plan_enforces_clarify_requirements(plan):
    with pytest.raises(PlanValidationError, match="clarif"):
        validate_plan(plan, _planner_input())


@pytest.mark.parametrize(
    "plan",
    [
        LeaderPlan(goal="flag forbidden", plan_type="direct_reply", needs_clarification=True),
        LeaderPlan(
            goal="question forbidden",
            plan_type="direct_reply",
            clarification_question="Unexpected question",
        ),
    ],
)
def test_validate_plan_rejects_clarification_fields_for_other_plans(plan):
    with pytest.raises(PlanValidationError, match="clarif"):
        validate_plan(plan, _planner_input())


def test_plan_schema_rejects_more_than_two_steps():
    with pytest.raises(ValidationError):
        LeaderPlan(
            goal="loop-like plan",
            plan_type="research_then_idea",
            steps=[
                PlanStep(id="research-1", agent="research", action="recommend_papers"),
                PlanStep(id="idea-1", agent="idea", action="generate_ideas"),
                PlanStep(id="idea-2", agent="idea", action="generate_ideas"),
            ],
        )
