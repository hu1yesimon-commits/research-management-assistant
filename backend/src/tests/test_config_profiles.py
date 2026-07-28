import pytest

from config import Config, config, load_config, validate_runtime_profile


REAL_PROVIDER_ENV = {
    "EMBEDDING_PROVIDER": "bge-m3",
    "VECTOR_BACKEND": "chroma",
    "ANSWER_PROVIDER": "deepseek",
    "LEADER_PROVIDER": "openai",
    "LEADER_RESPONSE_PROVIDER": "deepseek",
    "SUMMARY_PROVIDER": "openai",
    "PAPER_JUDGE_PROVIDER": "deepseek",
    "DEEPSEEK_API_KEY": "test-secret",
    "DEEPSEEK_BASE_URL": "https://provider.invalid/v1",
    "OPENALEX_API_KEY": "openalex-test-secret",
    "SEMANTIC_SCHOLAR_API_KEY": "semantic-test-secret",
}


def test_pytest_entrypoint_forces_test_profile_before_config_import():
    assert config.runtime_profile == "test"
    assert config.embedding_provider == "fake"
    assert config.vector_backend == "fake"
    assert config.answer_provider == "deterministic"
    assert config.leader_response_provider == "deterministic"


@pytest.mark.parametrize("runtime_profile", ["test", "offline-dev"])
def test_offline_profiles_ignore_real_provider_environment(runtime_profile):
    configured = load_config(
        {
            **REAL_PROVIDER_ENV,
            "RUNTIME_PROFILE": runtime_profile,
        }
    )

    assert configured.runtime_profile == runtime_profile
    assert configured.embedding_provider == "fake"
    assert configured.vector_backend == "fake"
    assert configured.answer_provider == "deterministic"
    assert configured.idea_provider == "deterministic"
    assert configured.leader_provider == "deterministic"
    assert configured.leader_response_provider == "deterministic"
    assert configured.summary_provider == "deterministic"
    assert configured.paper_judge_provider == "mock"
    assert configured.deepseek_api_key == ""
    assert configured.deepseek_base_url == ""
    assert configured.openalex_api_key == ""
    assert configured.semantic_scholar_api_key == ""


def test_default_profile_is_offline_even_with_real_provider_environment():
    configured = load_config(REAL_PROVIDER_ENV)

    assert configured.runtime_profile == "offline-dev"
    assert configured.embedding_provider == "fake"
    assert configured.vector_backend == "fake"
    assert configured.answer_provider == "deterministic"
    assert configured.leader_response_provider == "deterministic"


def test_real_smoke_profile_honors_explicit_provider_environment():
    configured = load_config(
        {
            **REAL_PROVIDER_ENV,
            "RUNTIME_PROFILE": "real-smoke",
        }
    )

    assert configured.runtime_profile == "real-smoke"
    assert configured.embedding_provider == "bge-m3"
    assert configured.vector_backend == "chroma"
    assert configured.answer_provider == "deepseek"
    assert configured.idea_provider == "deterministic"
    assert configured.leader_provider == "openai"
    assert configured.leader_response_provider == "deepseek"
    assert configured.summary_provider == "openai"
    assert configured.paper_judge_provider == "deepseek"
    assert configured.deepseek_api_key == "test-secret"
    assert configured.deepseek_base_url == "https://provider.invalid/v1"
    assert configured.openalex_api_key == "openalex-test-secret"
    assert configured.semantic_scholar_api_key == "semantic-test-secret"


def test_unknown_runtime_profile_fails_before_provider_construction():
    with pytest.raises(ValueError, match="Unsupported runtime profile"):
        load_config({"RUNTIME_PROFILE": "production"})

    with pytest.raises(ValueError, match="Unsupported runtime profile"):
        validate_runtime_profile("production")


def test_config_defaults_are_offline():
    configured = Config()

    assert configured.runtime_profile == "offline-dev"
    assert configured.leader_provider == "deterministic"
    assert configured.leader_response_provider == "deterministic"
