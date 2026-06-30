from typing import Literal

from pydantic import BaseModel, Field

from services.schemas import ExperimentLogRequest, IdeaResult, KnowledgeResult
from services.session_schemas import SessionContext


PlanType = Literal[
    "direct_reply",
    "knowledge_qa",
    "research",
    "idea",
    "research_then_idea",
    "clarify",
]
AgentName = Literal["knowledge", "research", "idea"]
AgentAction = Literal["answer", "recommend_papers", "generate_ideas"]


class PlanStep(BaseModel):
    id: str = Field(min_length=1)
    agent: AgentName
    action: AgentAction
    input: dict = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class LeaderPlan(BaseModel):
    goal: str = Field(min_length=1)
    plan_type: PlanType
    steps: list[PlanStep] = Field(default_factory=list, max_length=2)
    needs_clarification: bool = False
    clarification_question: str | None = None


class PlannerInput(BaseModel):
    message: str
    context: SessionContext
    experiment_log: ExperimentLogRequest | None = None
    has_knowledge: bool = False


class ResearchResult(BaseModel):
    enabled: Literal[True] = True
    batch_id: str | None = None
    requested_top_k: int
    returned_count: int
    top_k: list[dict] = Field(default_factory=list)
    rewritten_queries: list[str] = Field(default_factory=list)
    total_raw: int = 0
    total_deduped: int = 0
    error: str | None = None


class AgentTask(BaseModel):
    step: PlanStep
    session_id: str
    turn_id: str


class AgentError(BaseModel):
    agent_name: Literal["leader", "knowledge", "research", "idea"]
    stage: str
    message: str
    recoverable: bool = True


class AgentResult(BaseModel):
    agent_name: AgentName
    action: AgentAction
    status: Literal["completed", "failed", "skipped"]
    knowledge: KnowledgeResult | None = None
    research: ResearchResult | None = None
    idea: IdeaResult | None = None
    errors: list[AgentError] = Field(default_factory=list)


class AgentRunSummary(BaseModel):
    agent_name: str
    action: str
    status: Literal["completed", "failed", "skipped"]
