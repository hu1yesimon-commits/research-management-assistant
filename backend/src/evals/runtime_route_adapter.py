from __future__ import annotations

import argparse
from pathlib import Path

from agent_team.contracts import LeaderPlan, PlannerInput
from agent_team.planner import DeterministicLeaderPlanner
from agent_team.validator import PlanValidator
from evals.schema import (
    CaseObservation,
    GoldCase,
    GoldDataset,
    ObservationDataset,
    RouteObservation,
)
from services.session_schemas import SessionContext


class UnmappableRuntimeRouteError(ValueError):
    """Raised when a V3 plan does not prove one Gold business route."""


_ROUTE_BY_PLAN_TYPE = {
    "direct_reply": "direct_reply",
    "clarify": "clarify",
    "research": "discovery",
    "knowledge_qa": "knowledge_qa",
}

_ACTIONS_BY_RUNTIME_ACTION = {
    "answer": ("knowledge_qa", "grounded_answer"),
    "recommend_papers": ("discovery",),
}


def adapt_v3_route(plan: LeaderPlan) -> RouteObservation:
    route = _ROUTE_BY_PLAN_TYPE.get(plan.plan_type)
    if route is None:
        raise UnmappableRuntimeRouteError(
            f"V3 plan type {plan.plan_type!r} does not prove one Gold route"
        )
    PlanValidator().validate(plan)
    actions = []
    for step in plan.steps:
        for action in _ACTIONS_BY_RUNTIME_ACTION.get(step.action, ()):
            if action not in actions:
                actions.append(action)
    return RouteObservation(route=route, actions=actions)


def planner_input_from_gold_case(case: GoldCase) -> PlannerInput:
    message = next(
        (
            message.text
            for message in reversed(case.messages)
            if message.role == "user"
        ),
        None,
    )
    if message is None:
        raise ValueError(f"Gold case {case.case_id} has no user message")
    retrieved_chunks = (
        []
        if case.retrieval_fixture is None
        else case.retrieval_fixture.retrieved_chunks
    )
    return PlannerInput(
        message=message,
        context=SessionContext(session_id=f"eval-{case.case_id}"),
        experiment_log=None,
        has_knowledge=bool(retrieved_chunks),
    )


def build_v3_route_observations(
    gold: GoldDataset,
    planner: object | None = None,
) -> ObservationDataset:
    route_planner = planner or DeterministicLeaderPlanner()
    observations = []
    for case in gold.cases:
        if "route" not in case.scope:
            continue
        planner_input = planner_input_from_gold_case(case)
        plan = route_planner.plan(planner_input)
        observations.append(
            CaseObservation(
                case_id=case.case_id,
                scopes=["route"],
                route=adapt_v3_route(plan),
            )
        )
    return ObservationDataset(
        dataset=gold.dataset,
        version=gold.version,
        profile="runtime",
        cases=observations,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate route-only observations from the V3 deterministic planner."
    )
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    observations = build_v3_route_observations(
        GoldDataset.from_path(args.gold)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        observations.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
