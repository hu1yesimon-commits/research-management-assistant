from typing import Literal, TypedDict

from services.schemas import ExperimentLogRequest


AssistantIntent = Literal["auto", "search", "research"]
AssistantMode = Literal["basic", "advanced"]
AssistantRoute = Literal["basic_explore", "advanced_ready", "advanced_search", "research_idea"]


class ResearchAssistantState(TypedDict):
    query: str
    intent: AssistantIntent
    experiment_log: ExperimentLogRequest | None
    top_k: int
    idea_count: int
    save_log: bool
    include_discovery: bool
    memory_context: str
    coverage_retrieval_results: list[dict] | None
    coverage_score: float
    mode: AssistantMode
    route: AssistantRoute
    route_reason: str
    discovery: dict
    knowledge: dict
    ideas: list[dict]
    discovery_result: dict
    knowledge_result: dict
    idea_result: dict
    assistant_message: str
    next_action: dict | None
    suggested_user_actions: list[str]
    errors: list[dict]
