"""Bounded Leader planning and user-facing response generation."""

import json
import re
from typing import Protocol

from agent_team.contracts import (
    AgentResult,
    LeaderPlan,
    PlannerInput,
    PlanStep,
)
from agent_team.prompts import FEW_SHOT_CASES, LEADER_SYSTEM_PROMPT
from agent_team.providers import validate_provider_name
from agent_team.research_routing import ResearchRoutingParser


class LeaderPlanner(Protocol):
    def plan(self, planner_input: PlannerInput) -> LeaderPlan:
        """Return one bounded typed plan."""


class LeaderResponder(Protocol):
    def respond(
        self,
        planner_input: PlannerInput,
        plan: LeaderPlan,
        results: list[AgentResult],
    ) -> str:
        """Return the Leader's final user-facing message."""


def _bounded_plan(
    plan_type: str,
    goal: str,
    clarification_question: str | None = None,
) -> LeaderPlan:
    steps_by_type = {
        "direct_reply": [],
        "clarify": [],
        "knowledge_qa": [
            PlanStep(id="knowledge-1", agent="knowledge", action="answer")
        ],
        "research": [
            PlanStep(
                id="research-1",
                agent="research",
                action="recommend_papers",
            )
        ],
        "idea": [
            PlanStep(id="idea-1", agent="idea", action="generate_ideas")
        ],
        "research_then_idea": [
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
    }
    return LeaderPlan(
        goal=goal,
        plan_type=plan_type,
        steps=steps_by_type[plan_type],
        needs_clarification=plan_type == "clarify",
        clarification_question=clarification_question,
    )


class LeaderPromptBuilder:
    """Render reviewed examples and only the context needed for planning."""

    def messages(self, planner_input: PlannerInput) -> list[tuple[str, str]]:
        messages: list[tuple[str, str]] = [("system", LEADER_SYSTEM_PROMPT)]
        for case in FEW_SHOT_CASES:
            example_input = {
                "message": case["message"],
                "has_knowledge": case["has_knowledge"],
                "has_experiment_log": case["has_experiment_log"],
            }
            example_plan = _bounded_plan(
                case["plan_type"],
                case["message"],
                case.get("clarification_question"),
            )
            messages.extend(
                [
                    ("user", json.dumps(example_input, ensure_ascii=False)),
                    ("assistant", example_plan.model_dump_json()),
                ]
            )

        current_input = {
            "message": planner_input.message,
            "session_summary": planner_input.context.session_summary,
            "has_knowledge": planner_input.has_knowledge,
            "has_experiment_log": planner_input.experiment_log is not None,
            "experiment_log": (
                planner_input.experiment_log.model_dump()
                if planner_input.experiment_log is not None
                else None
            ),
        }
        messages.append(("user", json.dumps(current_input, ensure_ascii=False)))
        return messages


class StructuredLLMLeaderPlanner:
    def __init__(self, chat_model, prompt_builder: LeaderPromptBuilder | None = None):
        self.chat_model = chat_model
        self.prompt_builder = prompt_builder or LeaderPromptBuilder()

    def plan(self, planner_input: PlannerInput) -> LeaderPlan:
        structured_model = self.chat_model.with_structured_output(LeaderPlan)
        result = structured_model.invoke(self.prompt_builder.messages(planner_input))
        if not isinstance(result, LeaderPlan):
            raise TypeError("structured Leader provider must return LeaderPlan")
        return result


class DeterministicLeaderPlanner:
    """Offline routing for the fixed plan vocabulary."""

    def plan(self, planner_input: PlannerInput) -> LeaderPlan:
        message = planner_input.message.strip()
        normalized = message.lower()

        if self._is_product_capability_question(normalized):
            return _bounded_plan("direct_reply", message)

        research_signal = ResearchRoutingParser().parse(message)
        asks_for_ideas = self._contains_term(
            normalized,
            ("idea", "ideas", "propose", "next test", "direction"),
        )

        if research_signal.needs_clarify or research_signal.decision == "conflict":
            return _bounded_plan(
                "clarify",
                message,
                "Should the team search for fresh papers or use existing material?",
            )

        if asks_for_ideas:
            if planner_input.experiment_log is None:
                return _bounded_plan(
                    "clarify",
                    message,
                    "Please provide the experiment log before asking for ideas.",
                )
            if research_signal.decision == "allow":
                return _bounded_plan("research_then_idea", message)
            if planner_input.has_knowledge:
                return _bounded_plan("idea", message)
            if research_signal.decision in {"deny", "review_existing"}:
                return _bounded_plan(
                    "clarify",
                    message,
                    "Should the team search for fresh papers before generating ideas?",
                )
            return _bounded_plan("research_then_idea", message)

        if research_signal.decision == "allow":
            return _bounded_plan("research", message)

        if research_signal.decision == "review_existing":
            if planner_input.has_knowledge:
                return _bounded_plan("knowledge_qa", message)
            return _bounded_plan(
                "clarify",
                message,
                "Which saved research material should the team review?",
            )

        if self._asks_for_agent_creation(normalized):
            return _bounded_plan(
                "clarify",
                message,
                "The team has fixed Leader, Research, and Idea roles. What research "
                "outcome should the existing team produce?",
            )

        asks_about_saved_knowledge = planner_input.has_knowledge and self._contains_term(
            normalized, ("explain", "saved", "knowledge", "what do")
        )
        if asks_about_saved_knowledge:
            return _bounded_plan("knowledge_qa", message)

        if normalized in {"improve it", "improve", "make it better"}:
            return _bounded_plan(
                "clarify",
                message,
                "Which experiment, paper, or metric do you want to improve?",
            )

        return _bounded_plan(
            "clarify",
            message or "Clarify the research request",
            "What research question or outcome should the team work on?",
        )

    @staticmethod
    def _is_product_capability_question(message: str) -> bool:
        return any(
            phrase in message
            for phrase in (
                "what can this research workbench do",
                "what can you do",
                "how does this workbench work",
            )
        )

    @staticmethod
    def _contains_term(message: str, terms: tuple[str, ...]) -> bool:
        return any(
            re.search(rf"(?<!\w){re.escape(term)}(?!\w)", message)
            for term in terms
        )

    @staticmethod
    def _asks_for_agent_creation(message: str) -> bool:
        return bool(
            re.search(r"\b(?:create|add|spawn)\b.{0,40}\bagent\b", message)
        )

class DeterministicLeaderResponder:
    """Summarize typed execution outcomes without generating new evidence."""

    def respond(
        self,
        planner_input: PlannerInput,
        plan: LeaderPlan,
        results: list[AgentResult],
    ) -> str:
        if plan.plan_type == "clarify":
            return plan.clarification_question or "Please clarify the research request."
        if plan.plan_type == "direct_reply":
            return (
                "This research workbench can discover fresh papers, answer from saved "
                "knowledge, and propose experiment ideas when an experiment log is provided."
            )
        if not results:
            return "No agent results were produced for this plan."

        lines = []
        reported_errors: set[str] = set()
        for result in results:
            lines.append(
                f"{result.agent_name} {result.action}: {result.status}"
            )
            error_messages = [error.message for error in result.errors]
            for payload in (result.knowledge, result.research, result.idea):
                if payload is not None and payload.error:
                    error_messages.append(payload.error)
            for error_message in error_messages:
                if error_message not in reported_errors:
                    reported_errors.add(error_message)
                    lines.append(f"error: {error_message}")
        return "\n".join(lines)
