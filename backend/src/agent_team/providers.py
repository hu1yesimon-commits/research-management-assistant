"""Shared provider-name policy for agent-team dependencies."""

import os
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


def _build_chat_model_with_overrides(
    provider: str,
    *,
    model: str,
    temperature: float,
    deepseek_api_key: str,
    deepseek_base_url: str,
    chat_model_cls=None,
):
    validate_provider_name(provider)
    using_default_chat_model = chat_model_cls is None
    if chat_model_cls is None:
        from langchain_openai import ChatOpenAI

        chat_model_cls = ChatOpenAI

    kwargs = {
        "model": model,
        "temperature": temperature,
    }
    if using_default_chat_model and provider == "openai":
        kwargs["api_key"] = os.getenv("OPENAI_API_KEY", "missing-api-key")
    if provider == "deepseek":
        kwargs["api_key"] = deepseek_api_key or "missing-api-key"
        if deepseek_base_url:
            kwargs["base_url"] = deepseek_base_url
    return chat_model_cls(**kwargs)


def _build_chat_model(config: Any, provider: str, chat_model_cls=None):
    return _build_chat_model_with_overrides(
        provider,
        model=config.leader_model,
        temperature=config.leader_temperature,
        deepseek_api_key=config.deepseek_api_key,
        deepseek_base_url=config.deepseek_base_url,
        chat_model_cls=chat_model_cls,
    )


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


def build_leader_responder(config: Any, chat_model_cls=None):
    """Construct the configured user-facing Leader responder."""
    from agent_team.planner import DeterministicLeaderResponder, LLMLeaderResponder

    provider = validate_provider_name(config.leader_response_provider)
    if provider == "deterministic":
        return DeterministicLeaderResponder()
    if chat_model_cls is None and provider == "deepseek" and not config.deepseek_api_key:
        return LLMLeaderResponder(chat_model=None, enabled=False)
    if chat_model_cls is None and provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return LLMLeaderResponder(chat_model=None, enabled=False)
    return LLMLeaderResponder(
        _build_chat_model_with_overrides(
            provider,
            model=config.leader_response_model,
            temperature=config.leader_response_temperature,
            deepseek_api_key=config.deepseek_api_key,
            deepseek_base_url=config.deepseek_base_url,
            chat_model_cls=chat_model_cls,
        )
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
