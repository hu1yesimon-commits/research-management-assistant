from agent_team.contracts import AgentError, AgentResult
from services.idea_service import IdeaRecommendationService, IdeaServiceError
from services.schemas import ExperimentLogRequest, IdeaResult


class IdeaAgent:
    def __init__(self, idea_service: IdeaRecommendationService):
        self.idea_service = idea_service

    def run(
        self,
        experiment_log: ExperimentLogRequest,
        research_candidates: list[dict],
        idea_count: int,
    ) -> AgentResult:
        try:
            response = self.idea_service.recommend(
                experiment_log=experiment_log,
                include_discovery=False,
                discovery_candidates=list(research_candidates),
                idea_count=idea_count,
            )
        except IdeaServiceError as exc:
            return AgentResult(
                agent_name="idea",
                action="generate_ideas",
                status="failed",
                idea=IdeaResult(enabled=True, error=exc.detail),
                errors=[
                    AgentError(
                        agent_name="idea",
                        stage="idea_generation",
                        message=exc.detail,
                        recoverable=exc.status_code >= 500,
                    )
                ],
            )

        return AgentResult(
            agent_name="idea",
            action="generate_ideas",
            status="completed",
            idea=IdeaResult(
                enabled=True,
                ideas=response.ideas,
                supporting_evidence=[
                    evidence
                    for idea in response.ideas
                    for evidence in idea.supporting_evidence
                ],
                log_id=response.log_id,
            ),
        )
