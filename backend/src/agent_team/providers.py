"""Shared provider-name policy for agent-team dependencies."""

from typing import Any


SUPPORTED_PROVIDER_NAMES = frozenset({"deterministic", "openai", "deepseek"})


def validate_provider_name(provider: str) -> str:
    """Reject unknown providers before any dependency construction occurs."""
    if provider not in SUPPORTED_PROVIDER_NAMES:
        supported = ", ".join(sorted(SUPPORTED_PROVIDER_NAMES))
        raise ValueError(
            f"Unsupported provider {provider!r}; expected one of: {supported}"
        )
    return provider


def _build_chat_model(config: Any, provider: str, chat_model_cls=None):
    validate_provider_name(provider)
    if chat_model_cls is None:
        from langchain_openai import ChatOpenAI

        chat_model_cls = ChatOpenAI

    kwargs = {
        "model": config.leader_model,
        "temperature": config.leader_temperature,
    }
    if provider == "deepseek":
        kwargs.update(
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url,
        )
    return chat_model_cls(**kwargs)


def build_leader_planner(config: Any, chat_model_cls=None):
    """Construct the configured bounded Leader without network activity."""
    from agent_team.planner import (
        DeterministicLeaderPlanner,
        StructuredLLMLeaderPlanner,
    )

    provider = validate_provider_name(config.leader_provider)
    if provider == "deterministic":
        return DeterministicLeaderPlanner()
    return StructuredLLMLeaderPlanner(
        _build_chat_model(config, provider, chat_model_cls)
    )


def build_summary_generator(config: Any, chat_model_cls=None):
    """Construct the configured session summary generator."""
    from services.session_context import (
        DeterministicSummaryGenerator,
        LLMSummaryGenerator,
    )

    provider = validate_provider_name(config.summary_provider)
    if provider == "deterministic":
        return DeterministicSummaryGenerator()
    return LLMSummaryGenerator(
        _build_chat_model(config, provider, chat_model_cls)
    )
