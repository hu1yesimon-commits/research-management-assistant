import json
from pathlib import Path

import pytest

from agent_team.planner import DeterministicLeaderPlanner
from agent_team.validator import PlanValidator
from services.schemas import ExperimentLogRequest
from services.session_schemas import SessionContext
from agent_team.contracts import PlannerInput


def load_cases():
  path = (
    Path(__file__).resolve().parents[1]
    / "evals"
    / "leader_planner_cases.json"
  )
  return json.loads(path.read_text())


def planner_input_from_case(case):
  experiment_log = (
    ExperimentLogRequest(**case["experiment_log"])
    if case["experiment_log"] is not None
    else None
  )
  return PlannerInput(
    message=case["message"],
    context=SessionContext(session_id="default"),
    experiment_log=experiment_log,
    has_knowledge=case["has_knowledge"],
  )


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["id"])
def test_deterministic_planner_eval(case):
  planner_input = planner_input_from_case(case)
  plan = DeterministicLeaderPlanner().plan(planner_input)
  PlanValidator().validate(plan, experiment_log=planner_input.experiment_log)

  assert plan.plan_type == case["expected_plan_type"]
  actions = [step.action for step in plan.steps]
  assert not set(actions).intersection(case.get("forbidden_actions", []))
