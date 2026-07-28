import json
from typing import Protocol

from services.memory_store import MemoryStore
from services.session_schemas import SessionContext, StoredMessage
from services.session_store import SessionStore


AGENT_NAMES = ("leader", "research", "idea")


class SummaryGenerator(Protocol):
    def summarize(
        self, previous_summary: str, messages: list[StoredMessage]
    ) -> str:
        """Return a replacement rolling summary."""


class SessionContextBuilder:
    def __init__(
        self,
        session_store: SessionStore,
        memory_store: MemoryStore | None = None,
    ):
        self.session_store = session_store
        self.memory_store = memory_store or MemoryStore(str(session_store.database_path))

    def build(self, session_id: str) -> SessionContext:
        session = self.session_store.get_session(session_id)
        if session is None:
            raise ValueError(f"session not found: {session_id}")

        return SessionContext(
            session_id=session_id,
            session_summary=session["summary"],
            recent_messages=self.session_store.list_recent_turn_messages(
                session_id, turn_limit=6
            ),
            confirmed_memory=self.memory_store.build_confirmed_memory_context(),
            agent_contexts={
                agent_name: self.session_store.get_agent_context(
                    session_id, agent_name
                )
                for agent_name in AGENT_NAMES
            },
            current_knowledge=[],
        )


class DeterministicSummaryGenerator:
    def summarize(
        self, previous_summary: str, messages: list[StoredMessage]
    ) -> str:
        lines = [previous_summary.strip()] if previous_summary.strip() else []
        for message in messages:
            content = str(
                message.content.get("text")
                or message.content.get("assistant_message")
                or ""
            )[:400]
            line = f"{message.role}: {content}" if content else ""
            if line:
                lines.append(line)
        return "\n".join(lines)[-6000:]


class LLMSummaryGenerator:
    def __init__(self, chat_model):
        self.chat_model = chat_model

    def summarize(
        self, previous_summary: str, messages: list[StoredMessage]
    ) -> str:
        transcript = "\n".join(
            f"{message.role}: {json.dumps(message.content, ensure_ascii=False)}"
            for message in messages
        )
        response = self.chat_model.invoke(
            [
                (
                    "system",
                    "Compress the research conversation into factual goals, decisions, "
                    "evidence, and unresolved questions. Do not create long-term user "
                    "memory.",
                ),
                (
                    "user",
                    f"Previous summary:\n{previous_summary}\n\nNew messages:\n{transcript}",
                ),
            ]
        )
        if not isinstance(response.content, str) or not response.content.strip():
            raise ValueError("summary provider must return a non-empty string")
        return response.content.strip()


class SessionSummaryService:
    def __init__(
        self,
        session_store: SessionStore,
        generator: SummaryGenerator,
        threshold: int = 12,
    ):
        self.session_store = session_store
        self.generator = generator
        self.threshold = threshold

    def maybe_refresh(self, session_id: str) -> bool:
        if self.session_store.count_unsummarized_messages(session_id) < self.threshold:
            return False

        session = self.session_store.get_session(session_id)
        if session is None:
            return False
        messages = self.session_store.list_unsummarized_messages(session_id)
        if not messages:
            return False

        try:
            replacement = self.generator.summarize(session["summary"], messages)
        except Exception:
            return False

        return self.session_store.update_session_summary(
            session_id,
            replacement,
            messages[-1].id,
            expected_through_message_id=session["summary_through_message_id"],
        )
