import logging
import time
from collections.abc import Callable

from agent_team.contracts import (
    AgentResult,
    AgentRunSummary,
    LeaderPlan,
    PlannerInput,
)
from agent_team.dispatcher import TurnDeadlineExceeded
from agent_team.validator import PlanValidationError
from services.retrieval_service import RetrievalServiceError
from services.schemas import IdeaOption, KnowledgeResult
from services.session_schemas import SessionTurnRequest, SessionTurnResponse


logger = logging.getLogger(__name__)


class TurnTimeoutError(TimeoutError):
    """Raised after the bounded wall-clock deadline for a Turn expires."""


class ConversationService:
    def __init__(
        self,
        store: object,
        candidate_service: object,
        context_builder: object,
        knowledge_retrieval: object,
        planner: object,
        validator: object,
        dispatcher: object,
        responder: object,
        summary_service: object,
        turn_timeout_seconds: float = 30.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.candidate_service = candidate_service
        self.context_builder = context_builder
        self.knowledge_retrieval = knowledge_retrieval
        self.planner = planner
        self.validator = validator
        self.dispatcher = dispatcher
        self.responder = responder
        self.summary_service = summary_service
        self.turn_timeout_seconds = turn_timeout_seconds
        self.monotonic = monotonic

    def run(
        self, session_id: str, request: SessionTurnRequest
    ) -> SessionTurnResponse:
        start = self.store.start_turn(
            session_id,
            request.idempotency_key,
            {"text": request.message},
        )
        if start.replayed:
            replay = self.store.get_replayed_response(session_id, start.turn_id)
            if replay is not None:
                return SessionTurnResponse(**replay)
            return SessionTurnResponse(
                session_id=session_id,
                turn_id=start.turn_id,
                status=start.status,
            )

        deadline = self.monotonic() + self.turn_timeout_seconds
        try:
            context = self.context_builder.build(session_id)
            try:
                retrieval = self.knowledge_retrieval.search(
                    request.message,
                    top_k=request.top_k,
                )
                context = context.model_copy(
                    update={"current_knowledge": retrieval.results}
                )
            except RetrievalServiceError:
                context = context.model_copy(update={"current_knowledge": []})

            self._check_deadline(deadline)
            planner_input = self._planner_input(request, context)
            plan = self.planner.plan(planner_input)
            try:
                plan = self.validator.validate(
                    plan,
                    experiment_log=request.experiment_log,
                )
            except PlanValidationError as exc:
                plan = self._clarification_plan(request.message, str(exc))
                results: list[AgentResult] = []
            else:
                self._check_deadline(deadline)
                try:
                    results = self.dispatcher.execute(
                        session_id,
                        start.turn_id,
                        plan,
                        request.experiment_log,
                        context,
                        remaining_turn_seconds=lambda: deadline - self.monotonic(),
                    )
                except TurnDeadlineExceeded as exc:
                    raise TurnTimeoutError(str(exc)) from exc

            self._check_deadline(deadline)
            assistant_message = self.responder.respond(
                planner_input,
                plan,
                results,
            )
            response = self._response(
                session_id,
                start.turn_id,
                plan,
                results,
                assistant_message,
            )
            self.store.complete_turn(
                start.turn_id,
                response.model_dump(mode="json"),
                plan.model_dump(mode="json"),
            )
        except Exception as exc:
            self.store.fail_turn(start.turn_id, self._error_payload(exc))
            raise
        try:
            self.summary_service.maybe_refresh(session_id)
        except Exception:
            logger.exception("session summary refresh failed for %s", session_id)
        return response

    @staticmethod
    def _planner_input(request: SessionTurnRequest, context: object) -> PlannerInput:
        return PlannerInput(
            message=request.message,
            context=context,
            experiment_log=request.experiment_log,
            has_knowledge=bool(context.current_knowledge),
        )

    def _response(
        self,
        session_id: str,
        turn_id: str,
        plan: LeaderPlan,
        results: list[AgentResult],
        assistant_message: str,
    ) -> SessionTurnResponse:
        knowledge = KnowledgeResult(enabled=False)
        ideas: list[IdeaOption] = []
        for result in results:
            if result.status == "completed" and result.knowledge is not None:
                knowledge = result.knowledge
            if result.status == "completed" and result.idea is not None:
                ideas.extend(result.idea.ideas)
        return SessionTurnResponse(
            session_id=session_id,
            turn_id=turn_id,
            status="completed",
            assistant_message=assistant_message,
            plan=plan,
            active_candidates=self.candidate_service.list_active(session_id),
            knowledge=knowledge,
            ideas=ideas,
            agent_runs=[
                AgentRunSummary(
                    agent_name=result.agent_name,
                    action=result.action,
                    status=result.status,
                )
                for result in results
            ],
            errors=[error for result in results for error in result.errors],
        )

    def _check_deadline(self, deadline: float) -> None:
        if self.monotonic() >= deadline:
            raise TurnTimeoutError(
                f"turn exceeded {self.turn_timeout_seconds} seconds"
            )

    @staticmethod
    def _clarification_plan(message: str, reason: str) -> LeaderPlan:
        return LeaderPlan(
            goal=message,
            plan_type="clarify",
            needs_clarification=True,
            clarification_question=(
                "The requested workflow was not valid. Please clarify the desired "
                f"research outcome. ({reason})"
            ),
        )

    @staticmethod
    def _error_payload(exc: Exception) -> dict:
        if isinstance(exc, TurnTimeoutError):
            return {"stage": "timeout", "message": str(exc)}
        return {
            "stage": "orchestration",
            "type": type(exc).__name__,
            "message": str(exc),
        }
