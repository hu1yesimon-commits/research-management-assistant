from typing import Literal

from pydantic import BaseModel, Field

from services.schemas import JudgeResult, KnowledgeSearchResult, PaperMetadata


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
