"""Shared provider-name policy for agent-team dependencies."""


SUPPORTED_PROVIDER_NAMES = frozenset({"deterministic", "openai", "deepseek"})


def validate_provider_name(provider: str) -> str:
    """Reject unknown providers before any dependency construction occurs."""
    if provider not in SUPPORTED_PROVIDER_NAMES:
        supported = ", ".join(sorted(SUPPORTED_PROVIDER_NAMES))
        raise ValueError(
            f"Unsupported provider {provider!r}; expected one of: {supported}"
        )
    return provider
