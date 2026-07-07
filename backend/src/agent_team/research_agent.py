from graph.errors import DiscoveryStageError
from agent_team.contracts import AgentError, AgentResult, ResearchResult


class ResearchAgent:
    def __init__(self, discovery_graph: object, candidate_service: object):
        self.discovery_graph = discovery_graph
        self.candidate_service = candidate_service

    def run(
        self,
        session_id: str,
        turn_id: str,
        query: str,
        memory_context: str,
        top_k: int,
    ) -> AgentResult:
        try:
            graph_result = self.discovery_graph.invoke(
                {
                    "mode": "advanced",
                    "user_query": query,
                    "memory_context": memory_context,
                    "memory_context_is_snapshot": True,
                    "rewritten_queries": [],
                    "raw_results": [],
                    "normalized_papers": [],
                    "deduped_papers": [],
                    "judge_results": [],
                    "judge_failures": [],
                    "ranked_candidates": [],
                }
            )
        except DiscoveryStageError as exc:
            return AgentResult(
                agent_name="research",
                action="recommend_papers",
                status="failed",
                research=ResearchResult(
                    requested_top_k=top_k,
                    returned_count=0,
                    error=exc.detail,
                ),
                errors=[
                    AgentError(
                        agent_name="research",
                        stage=exc.stage,
                        message=exc.detail,
                        recoverable=exc.recoverable,
                    )
                ],
            )

        fresh = self.candidate_service.filter_fresh(
            session_id,
            graph_result.get("ranked_candidates", []),
            top_k,
        )
        batch = (
            self.candidate_service.create_batch(
                session_id, turn_id, query, fresh
            )
            if fresh
            else None
        )
        judge_errors = [
            AgentError(
                agent_name="research",
                stage="llm_judge",
                message=failure,
                recoverable=True,
            )
            for failure in graph_result.get("judge_failures", [])
        ]
        return AgentResult(
            agent_name="research",
            action="recommend_papers",
            status="completed",
            research=ResearchResult(
                batch_id=None if batch is None else batch.id,
                requested_top_k=top_k,
                returned_count=len(fresh),
                top_k=fresh,
                rewritten_queries=graph_result.get("rewritten_queries", []),
                total_raw=len(graph_result.get("raw_results", [])),
                total_deduped=len(graph_result.get("deduped_papers", [])),
            ),
            errors=judge_errors,
        )
