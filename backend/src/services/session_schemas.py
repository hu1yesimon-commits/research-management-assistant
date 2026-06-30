from typing import Literal

from pydantic import BaseModel, Field


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


class MessagePage(BaseModel):
    items: list[StoredMessage] = Field(default_factory=list)
    next_before_id: int | None = None
