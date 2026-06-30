from agent_team.contracts import LeaderPlan, PlannerInput


class PlanValidationError(ValueError):
    """Raised when a typed plan violates the frozen bounded-plan rules."""


_EXPECTED_STEPS = {
    "direct_reply": [],
    "clarify": [],
    "knowledge_qa": [("knowledge", "answer")],
    "research": [("research", "recommend_papers")],
    "idea": [("idea", "generate_ideas")],
    "research_then_idea": [
        ("research", "recommend_papers"),
        ("idea", "generate_ideas"),
    ],
}


def validate_plan(plan: LeaderPlan, planner_input: PlannerInput) -> LeaderPlan:
    actual_steps = [(step.agent, step.action) for step in plan.steps]
    expected_steps = _EXPECTED_STEPS[plan.plan_type]
    if actual_steps != expected_steps:
        raise PlanValidationError(
            f"step sequence for {plan.plan_type!r} must be exactly {expected_steps!r}"
        )

    step_ids = [step.id for step in plan.steps]
    if len(step_ids) != len(set(step_ids)):
        raise PlanValidationError("step ids must be unique")

    if plan.plan_type == "research_then_idea":
        first_step, second_step = plan.steps
        if first_step.depends_on or second_step.depends_on != [first_step.id]:
            raise PlanValidationError(
                "research_then_idea depends_on must be empty for the first step "
                "and exactly the first step id for the second step"
            )
    elif any(step.depends_on for step in plan.steps):
        raise PlanValidationError("depends_on is forbidden for this plan type")

    if plan.plan_type in {"idea", "research_then_idea"} and planner_input.experiment_log is None:
        raise PlanValidationError(f"{plan.plan_type} requires experiment_log")

    if plan.plan_type == "clarify":
        if not plan.needs_clarification or not (plan.clarification_question or "").strip():
            raise PlanValidationError(
                "clarify requires needs_clarification and a nonempty clarification_question"
            )
    elif plan.needs_clarification or plan.clarification_question is not None:
        raise PlanValidationError(
            "clarification fields are forbidden for non-clarify plans"
        )

    return plan
