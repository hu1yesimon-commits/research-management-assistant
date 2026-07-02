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


class ResearchIntentParser:
    """Recognize bounded requests to retrieve academic material."""

    REQUEST_VERBS = frozenset(
        {"find", "search", "discover", "recommend", "show", "need", "review"}
    )
    ACADEMIC_TARGETS = frozenset(
        {
            "paper",
            "papers",
            "literature",
            "study",
            "studies",
            "article",
            "articles",
            "evidence",
            "method",
            "methods",
        }
    )
    NEGATIONS = frozenset({"no", "not", "never"})
    NON_ACADEMIC_PAPER_COMPOUNDS = frozenset(
        {"towel", "towels", "plate", "plates", "bag", "bags", "cup", "cups"}
    )
    MAX_TARGET_DISTANCE = 8

    def matches(self, message: str) -> bool:
        tokens = self._tokenize(message)
        for verb_index, target_start in self._request_starts(tokens):
            target_limit = min(
                len(tokens), target_start + self.MAX_TARGET_DISTANCE + 1
            )
            for target_index in range(target_start, target_limit):
                if self._is_negated(tokens, verb_index, target_index):
                    continue
                if self._is_academic_target(tokens, target_index):
                    return True
        return False

    @staticmethod
    def _tokenize(message: str) -> list[str]:
        normalized = message.lower().replace("don't", "do not")
        return re.findall(r"[a-z0-9]+", normalized)

    def _request_starts(self, tokens: list[str]):
        for index, token in enumerate(tokens):
            if token in self.REQUEST_VERBS:
                target_start = index + 1
                if target_start < len(tokens) and tokens[target_start] == "for":
                    target_start += 1
                yield index, target_start
            elif token == "look" and tokens[index : index + 2] == ["look", "for"]:
                yield index, index + 2

    def _is_negated(
        self, tokens: list[str], verb_index: int, target_index: int
    ) -> bool:
        prefix_start = max(0, verb_index - 3)
        return any(
            token in self.NEGATIONS
            for token in tokens[prefix_start:target_index]
        )

    def _is_academic_target(self, tokens: list[str], index: int) -> bool:
        token = tokens[index]
        if token not in self.ACADEMIC_TARGETS:
            return False
        return not (
            token == "paper"
            and index + 1 < len(tokens)
            and tokens[index + 1] in self.NON_ACADEMIC_PAPER_COMPOUNDS
        )


class DeterministicLeaderPlanner:
    """Offline routing for the fixed plan vocabulary."""

    def plan(self, planner_input: PlannerInput) -> LeaderPlan:
        message = planner_input.message.strip()
        normalized = message.lower()

        if self._is_product_capability_question(normalized):
            return _bounded_plan("direct_reply", message)

        asks_for_research = ResearchIntentParser().matches(normalized)
        asks_for_ideas = self._contains_term(
            normalized,
            ("idea", "ideas", "propose", "next test", "direction"),
        )

        if asks_for_research and asks_for_ideas:
            if planner_input.experiment_log is None:
                return _bounded_plan(
                    "clarify",
                    message,
                    "Please provide the experiment log before asking for ideas.",
                )
            return _bounded_plan("research_then_idea", message)

        if asks_for_ideas:
            if planner_input.experiment_log is None:
                return _bounded_plan(
                    "clarify",
                    message,
                    "Please provide the experiment log before asking for ideas.",
                )
            if planner_input.has_knowledge:
                return _bounded_plan("idea", message)
            return _bounded_plan("research_then_idea", message)

        if asks_for_research:
            return _bounded_plan("research", message)

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
