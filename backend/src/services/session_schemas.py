from typing import Literal

from pydantic import BaseModel, Field

from services.schemas import (
    ExperimentLogRequest,
    IdeaOption,
    JudgeResult,
    KnowledgeResult,
    KnowledgeSearchResult,
    PaperMetadata,
)


class StartTurnResult(BaseModel):
    turn_id: str
    status: Literal["running", "completed", "failed"]
    replayed: bool = False


class StoredMessage(BaseModel):
    id: int
    session_id: str
    turn_id: str
    role: Literal["user", "assistant", "agent", "system"]
    agent_name: str | None = None
    content: dict
    created_at: str


class SessionContext(BaseModel):
    session_id: str
    session_summary: str = ""
    recent_messages: list[StoredMessage] = Field(default_factory=list)
    confirmed_memory: str = ""
    agent_contexts: dict[str, str] = Field(default_factory=dict)
    current_knowledge: list[KnowledgeSearchResult] = Field(default_factory=list)


class MessagePage(BaseModel):
    items: list[StoredMessage] = Field(default_factory=list)
    next_before_id: int | None = None


class SessionCandidate(BaseModel):
    id: str
    batch_id: str
    paper_key: str
    paper_snapshot: PaperMetadata
    judgement: JudgeResult | None = None
    status: Literal["active", "accepted", "expired"]


class CandidateBatch(BaseModel):
    id: str
    session_id: str
    turn_id: str
    query: str
    status: Literal["active", "expired"]
    candidates: list[SessionCandidate] = Field(default_factory=list)


class CandidateAcceptResponse(BaseModel):
    candidate_id: str
    paper_id: str
    status: Literal["accepted"] = "accepted"


class SavedPaper(BaseModel):
    paper_id: str
    title: str
    doi: str | None = None
    source: str
    authors: list[str] = Field(default_factory=list)
    status: Literal["accepted", "uploaded", "chunked", "embedded"]
    pdf_path: str | None = None


class SessionTurnRequest(BaseModel):
    message: str = Field(min_length=1)
    experiment_log: ExperimentLogRequest | None = None
    idempotency_key: str = Field(min_length=1, max_length=128)
    top_k: int = Field(default=5, ge=1, le=20)
    idea_count: int = Field(default=3, ge=3, le=5)


from agent_team.contracts import AgentError, AgentRunSummary, LeaderPlan


class SessionTurnResponse(BaseModel):
    session_id: str
    turn_id: str
    status: Literal["running", "completed", "failed"]
    assistant_message: str = ""
    plan: LeaderPlan | None = None
    active_candidates: list[SessionCandidate] = Field(default_factory=list)
    knowledge: KnowledgeResult = Field(
        default_factory=lambda: KnowledgeResult(enabled=False)
    )
    ideas: list[IdeaOption] = Field(default_factory=list)
    agent_runs: list[AgentRunSummary] = Field(default_factory=list)
    errors: list[AgentError] = Field(default_factory=list)
