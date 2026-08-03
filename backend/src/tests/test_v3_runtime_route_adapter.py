from pathlib import Path

import pytest

from agent_team.contracts import LeaderPlan, PlanStep
from evals.evaluator import evaluate_dataset
from evals.runtime_route_adapter import (
    UnmappableRuntimeRouteError,
    adapt_v3_route,
    build_v3_route_observations,
    main,
    planner_input_from_gold_case,
)
from evals.schema import GoldDataset, ObservationDataset


ROOT = Path(__file__).resolve().parents[3]
GOLD_PATH = (
    ROOT / "docs" / "superpowers" / "evals" / "research-agent-gold-v0.json"
)


@pytest.fixture
def gold():
    return GoldDataset.from_path(GOLD_PATH)


@pytest.mark.parametrize(
    ("plan", "expected_route", "expected_actions"),
    [
        (
            LeaderPlan(goal="reply", plan_type="direct_reply"),
            "direct_reply",
            [],
        ),
        (
            LeaderPlan(
                goal="clarify",
                plan_type="clarify",
                needs_clarification=True,
                clarification_question="What should the team do?",
            ),
            "clarify",
            [],
        ),
        (
            LeaderPlan(
                goal="search",
                plan_type="research",
                steps=[
                    PlanStep(
                        id="research-1",
                        agent="research",
                        action="recommend_papers",
                    )
                ],
            ),
            "discovery",
            ["discovery"],
        ),
        (
            LeaderPlan(
                goal="answer",
                plan_type="knowledge_qa",
                steps=[
                    PlanStep(
                        id="knowledge-1",
                        agent="knowledge",
                        action="answer",
                    )
                ],
            ),
            "knowledge_qa",
            ["knowledge_qa", "grounded_answer"],
        ),
    ],
)
def test_adapter_maps_only_proven_runtime_routes(
    plan, expected_route, expected_actions
):
    observation = adapt_v3_route(plan)

    assert observation.route == expected_route
    assert observation.actions == expected_actions


@pytest.mark.parametrize("plan_type", ["idea", "research_then_idea"])
def test_adapter_rejects_ambiguous_runtime_routes(plan_type):
    plan = LeaderPlan(
        goal="ideas",
        plan_type=plan_type,
        steps=[
            PlanStep(
                id="idea-1",
                agent="idea",
                action="generate_ideas",
            )
        ],
    )

    with pytest.raises(
        UnmappableRuntimeRouteError,
        match="does not prove one Gold route",
    ):
        adapt_v3_route(plan)


def test_gold_input_uses_retrieved_presence_without_label_leakage(gold):
    case = next(
        case
        for case in gold.cases
        if case.case_id == "exp-sensor-drift-fallback-002"
    )

    planner_input = planner_input_from_gold_case(case)

    assert case.retrieval_fixture.relevant_chunk_ids == []
    assert planner_input.has_knowledge is True
    assert planner_input.experiment_log is None


def test_runtime_route_baseline_is_two_of_eight(gold):
    observations = build_v3_route_observations(gold)

    report = evaluate_dataset(gold, observations)

    assert report.evaluated_case_count == 8
    assert report.evaluated_scopes == ["route"]
    assert report.component_scores["route"]["exact_match_rate"] == 0.25
    assert report.hard_gate_summary["failed_case_count"] == 6
    assert report.performance_claim_valid is False
    assert {
        case.case_id for case in report.cases if case.hard_gates_passed
    } == {
        "exp-missing-context-clarify-003",
        "exp-explicit-fresh-discovery-008",
    }


def test_runtime_route_baseline_does_not_read_expected_route(gold):
    baseline = build_v3_route_observations(gold)
    mutated_gold = gold.model_copy(
        update={
            "cases": [
                case.model_copy(update={"expected_route": "memory_command"})
                for case in gold.cases
            ]
        }
    )

    mutated = build_v3_route_observations(mutated_gold)

    assert [
        case.route.route for case in mutated.cases
    ] == [
        case.route.route for case in baseline.cases
    ]


def test_runtime_route_adapter_cli_writes_observation_artifact(
    gold, tmp_path
):
    output_path = tmp_path / "runtime-route-observations.json"

    exit_code = main(
        ["--gold", str(GOLD_PATH), "--output", str(output_path)]
    )

    observations = ObservationDataset.from_path(output_path)
    assert exit_code == 0
    assert observations.profile == "runtime"
    assert len(observations.cases) == 8
    assert all(case.scopes == ["route"] for case in observations.cases)
