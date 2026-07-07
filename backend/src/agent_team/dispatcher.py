from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Protocol

from agent_team.contracts import (
    AgentError,
    AgentResult,
    LeaderPlan,
    PlanStep,
)
from services.qa_service import QAServiceError
from services.schemas import ExperimentLogRequest, KnowledgeResult
from services.session_schemas import SessionContext


class TurnDeadlineExceeded(TimeoutError):
    """Raised when the enclosing Turn budget is exhausted between Agent steps."""


class AgentDispatcher(Protocol):
    def execute(
        self,
        session_id: str,
        turn_id: str,
        plan: LeaderPlan,
        experiment_log: ExperimentLogRequest | None,
        context: SessionContext,
        remaining_turn_seconds: Callable[[], float] | None = None,
    ) -> list[AgentResult]:
        """Execute a validated bounded plan."""


class DirectAgentDispatcher:
    def __init__(
        self,
        knowledge_service: object,
        research_agent: object,
        idea_agent: object,
        session_store: object,
        agent_step_timeout_seconds: float,
    ) -> None:
        self.knowledge_service = knowledge_service
        self.research_agent = research_agent
        self.idea_agent = idea_agent
        self.session_store = session_store
        self.agent_step_timeout_seconds = agent_step_timeout_seconds

    def execute(
        self,
        session_id: str,
        turn_id: str,
        plan: LeaderPlan,
        experiment_log: ExperimentLogRequest | None,
        context: SessionContext,
        remaining_turn_seconds: Callable[[], float] | None = None,
    ) -> list[AgentResult]:
        results: list[AgentResult] = []
        results_by_step: dict[str, AgentResult] = {}

        for step in plan.steps:
            turn_budget = (
                None if remaining_turn_seconds is None else remaining_turn_seconds()
            )
            if turn_budget is not None and turn_budget <= 0:
                raise TurnDeadlineExceeded("turn deadline expired before agent step")
            run_id = self.session_store.start_agent_run(
                session_id,
                turn_id,
                step.agent,
                step.action,
                step.input,
            )
            if any(
                dependency not in results_by_step
                or results_by_step[dependency].status != "completed"
                for dependency in step.depends_on
            ):
                result = self._skipped_result(step)
                self.session_store.finish_agent_run(
                    run_id,
                    "skipped",
                    error=[error.model_dump() for error in result.errors],
                )
            else:
                result = self._execute_step(
                    run_id,
                    session_id,
                    turn_id,
                    step,
                    experiment_log,
                    context,
                    results_by_step,
                    turn_budget,
                )
                if result.status == "completed":
                    self._persist_context(session_id, step, result, experiment_log, context)

            results.append(result)
            results_by_step[step.id] = result

        return results

    def _execute_step(
        self,
        run_id: str,
        session_id: str,
        turn_id: str,
        step: PlanStep,
        experiment_log: ExperimentLogRequest | None,
        context: SessionContext,
        results_by_step: dict[str, AgentResult],
        turn_budget_seconds: float | None,
    ) -> AgentResult:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            self._call_step,
            session_id,
            turn_id,
            step,
            experiment_log,
            context,
            results_by_step,
        )
        step_timeout = self.agent_step_timeout_seconds
        turn_limited = False
        if turn_budget_seconds is not None:
            step_timeout = min(step_timeout, turn_budget_seconds)
            turn_limited = turn_budget_seconds <= self.agent_step_timeout_seconds
        try:
            result = future.result(timeout=step_timeout)
        except FutureTimeoutError:
            result = AgentResult(
                agent_name=step.agent,
                action=step.action,
                status="failed",
                errors=[
                    AgentError(
                        agent_name=step.agent,
                        stage="timeout",
                        message=f"agent step exceeded {step_timeout} seconds",
                    )
                ],
            )
            self.session_store.finish_agent_run(
                run_id,
                "failed",
                error=[error.model_dump() for error in result.errors],
            )
            executor.shutdown(wait=False, cancel_futures=True)
            if turn_limited:
                raise TurnDeadlineExceeded(
                    "turn deadline expired during agent step"
                )
            return result
        except Exception as exc:
            self.session_store.finish_agent_run(
                run_id,
                "failed",
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)

        self.session_store.finish_agent_run(
            run_id,
            result.status,
            output=result.model_dump() if result.status == "completed" else None,
            error=(
                [error.model_dump() for error in result.errors]
                if result.status == "failed"
                else None
            ),
        )
        return result

    def _call_step(
        self,
        session_id: str,
        turn_id: str,
        step: PlanStep,
        experiment_log: ExperimentLogRequest | None,
        context: SessionContext,
        results_by_step: dict[str, AgentResult],
    ) -> AgentResult:
        if step.agent == "knowledge":
            try:
                response = self.knowledge_service.answer(
                    question=step.input.get("question", ""),
                    top_k=step.input.get("top_k", 5),
                    retrieved_results=context.current_knowledge,
                )
            except QAServiceError as exc:
                return AgentResult(
                    agent_name="knowledge",
                    action="answer",
                    status="failed",
                    knowledge=KnowledgeResult(enabled=True, error=exc.detail),
                    errors=[
                        AgentError(
                            agent_name="knowledge",
                            stage="knowledge_answer",
                            message=exc.detail,
                            recoverable=True,
                        )
                    ],
                )
            return AgentResult(
                agent_name="knowledge",
                action="answer",
                status="completed",
                knowledge=KnowledgeResult(
                    enabled=True,
                    answer=response.answer,
                    sources=response.sources,
                    mode=response.mode,
                ),
            )

        if step.agent == "research":
            return self.research_agent.run(
                session_id=session_id,
                turn_id=turn_id,
                query=step.input.get("query", ""),
                memory_context=context.agent_contexts.get("research", ""),
                top_k=step.input.get("top_k", 5),
            )

        if experiment_log is None:
            raise ValueError("idea step requires experiment_log")
        research_candidates: list[dict] = []
        if step.depends_on:
            dependency = results_by_step[step.depends_on[0]]
            if dependency.research is not None:
                research_candidates = dependency.research.top_k
        return self.idea_agent.run(
            experiment_log=experiment_log,
            research_candidates=research_candidates,
            idea_count=step.input.get("idea_count", 3),
        )

    def _persist_context(
        self,
        session_id: str,
        step: PlanStep,
        result: AgentResult,
        experiment_log: ExperimentLogRequest | None,
        context: SessionContext,
    ) -> None:
        if step.agent == "research" and result.research is not None:
            summary = (
                f"query={step.input.get('query', '')}; "
                f"returned={result.research.returned_count}; "
                f"accepted_saved_context={len(context.current_knowledge)}"
            )
        elif step.agent == "idea" and result.idea is not None and experiment_log is not None:
            summary = (
                f"experiment={experiment_log.task}; ideas="
                f"{', '.join(idea.title for idea in result.idea.ideas)}"
            )
        elif step.agent == "knowledge" and result.knowledge is not None:
            summary = (
                f"question={step.input.get('question', '')}; "
                f"sources={len(result.knowledge.sources)}"
            )
        else:
            return
        self.session_store.upsert_agent_context(
            session_id,
            step.agent,
            summary,
            self.session_store.latest_message_id(session_id),
        )

    @staticmethod
    def _skipped_result(step: PlanStep) -> AgentResult:
        return AgentResult(
            agent_name=step.agent,
            action=step.action,
            status="skipped",
            errors=[
                AgentError(
                    agent_name=step.agent,
                    stage="dependency",
                    message="a required dependency did not complete",
                )
            ],
        )
