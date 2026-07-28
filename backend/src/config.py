import os
from dataclasses import dataclass
from typing import Mapping

from dotenv import load_dotenv

from agent_team.providers import validate_provider_name

load_dotenv()


SUPPORTED_RUNTIME_PROFILES = frozenset({"test", "offline-dev", "real-smoke"})
DEFAULT_RUNTIME_PROFILE = "offline-dev"


def validate_runtime_profile(profile: str) -> str:
    if profile not in SUPPORTED_RUNTIME_PROFILES:
        supported = ", ".join(sorted(SUPPORTED_RUNTIME_PROFILES))
        raise ValueError(
            f"Unsupported runtime profile {profile!r}; expected one of: {supported}"
        )
    return profile


@dataclass
class Config:
    runtime_profile: str = DEFAULT_RUNTIME_PROFILE

    # arXiv
    arxiv_enabled: bool = True
    arxiv_rate_limit: float = 3.0
    arxiv_max_results: int = 10
    arxiv_sort_by: str = "submittedDate"
    arxiv_sort_order: str = "descending"

    # openalex
    openalex_enabled: bool = True
    openalex_api_key: str = ""
    openalex_mailto: str = ""
    openalex_rate_limit: float = 1.0
    openalex_max_results: int = 10

    # Semantic Scholar (预留)
    semantic_scholar_enabled: bool = False
    semantic_scholar_api_key: str = ""
    semantic_scholar_rate_limit: float = 1.0

    # 全局
    paper_search_cache_enabled: bool = True
    paper_search_timeout: int = 20
    paper_max_results_per_source: int = 10
    database_path: str = "backend/data/research_memory.sqlite3"
    pdf_upload_dir: str = "backend/data/uploads"
    vector_store_dir: str = "backend/data/vector_store"
    vector_backend: str = "fake"
    chroma_persist_dir: str = "backend/data/vector_store/chroma"
    chroma_collection_name: str = "research_chunks"
    embedding_provider: str = "fake"
    bge_m3_model_name: str = "BAAI/bge-m3"
    answer_provider: str = "deterministic"
    answer_model: str = "deepseek-chat"
    answer_temperature: float = 0.0
    idea_provider: str = "deterministic"
    idea_model: str = "deepseek-chat"
    idea_temperature: float = 0.0
    leader_provider: str = "deterministic"
    leader_model: str = "deepseek-chat"
    leader_temperature: float = 0.0
    leader_response_provider: str = "deterministic"
    leader_response_model: str = "deepseek-chat"
    leader_response_temperature: float = 0.2
    summary_provider: str = "deterministic"
    agent_step_timeout_seconds: float = 120.0
    turn_timeout_seconds: float = 240.0
    paper_judge_provider: str = "mock"
    paper_judge_model: str = "deepseek-chat"
    deepseek_api_key: str = ""
    deepseek_base_url: str = ""
    deepseek_model: str = "deepseek-chat"

    def __post_init__(self):
        self.runtime_profile = validate_runtime_profile(self.runtime_profile)
        self.leader_provider = validate_provider_name(self.leader_provider)
        self.leader_response_provider = validate_provider_name(
            self.leader_response_provider
        )
        self.summary_provider = validate_provider_name(self.summary_provider)


def load_config(env: Mapping[str, str] | None = None) -> Config:
    source = os.environ if env is None else env
    runtime_profile = validate_runtime_profile(
        source.get("RUNTIME_PROFILE", DEFAULT_RUNTIME_PROFILE)
    )
    real_providers_enabled = runtime_profile == "real-smoke"

    def provider_setting(name: str, offline_default: str) -> str:
        if not real_providers_enabled:
            return offline_default
        return source.get(name, offline_default)

    return Config(
        runtime_profile=runtime_profile,
        arxiv_max_results=int(source.get("ARXIV_MAX_RESULTS", "10")),
        arxiv_rate_limit=float(source.get("ARXIV_RATE_LIMIT_SECONDS", "3.0")),
        arxiv_sort_by=source.get("ARXIV_SORT_BY", "submittedDate"),
        arxiv_sort_order=source.get("ARXIV_SORT_ORDER", "descending"),
        openalex_api_key=(
            source.get("OPENALEX_API_KEY", "") if real_providers_enabled else ""
        ),
        openalex_mailto=source.get("OPENALEX_MAILTO", ""),
        openalex_rate_limit=float(source.get("OPENALEX_RATE_LIMIT_SECONDS", "1.0")),
        openalex_max_results=int(source.get("OPENALEX_MAX_RESULTS", "10")),
        semantic_scholar_api_key=(
            source.get("SEMANTIC_SCHOLAR_API_KEY", "") if real_providers_enabled else ""
        ),
        semantic_scholar_rate_limit=float(
            source.get("SEMANTIC_SCHOLAR_RATE_LIMIT_SECONDS", "1.0")
        ),
        database_path=source.get(
            "DATABASE_PATH", "backend/data/research_memory.sqlite3"
        ),
        pdf_upload_dir=source.get("PDF_UPLOAD_DIR", "backend/data/uploads"),
        vector_store_dir=source.get("VECTOR_STORE_DIR", "backend/data/vector_store"),
        vector_backend=provider_setting("VECTOR_BACKEND", "fake"),
        chroma_persist_dir=source.get(
            "CHROMA_PERSIST_DIR", "backend/data/vector_store/chroma"
        ),
        chroma_collection_name=source.get("CHROMA_COLLECTION_NAME", "research_chunks"),
        embedding_provider=provider_setting("EMBEDDING_PROVIDER", "fake"),
        bge_m3_model_name=source.get("BGE_M3_MODEL_NAME", "BAAI/bge-m3"),
        answer_provider=provider_setting("ANSWER_PROVIDER", "deterministic"),
        answer_model=source.get(
            "ANSWER_MODEL", source.get("DEEPSEEK_MODEL", "deepseek-chat")
        ),
        answer_temperature=float(source.get("ANSWER_TEMPERATURE", "0")),
        idea_provider=provider_setting("IDEA_PROVIDER", "deterministic"),
        idea_model=source.get(
            "IDEA_MODEL", source.get("DEEPSEEK_MODEL", "deepseek-chat")
        ),
        idea_temperature=float(source.get("IDEA_TEMPERATURE", "0")),
        leader_provider=provider_setting("LEADER_PROVIDER", "deterministic"),
        leader_model=source.get("LEADER_MODEL", "deepseek-chat"),
        leader_temperature=float(source.get("LEADER_TEMPERATURE", "0")),
        leader_response_provider=provider_setting(
            "LEADER_RESPONSE_PROVIDER", "deterministic"
        ),
        leader_response_model=source.get(
            "LEADER_RESPONSE_MODEL",
            source.get("DEEPSEEK_MODEL", "deepseek-chat"),
        ),
        leader_response_temperature=float(
            source.get("LEADER_RESPONSE_TEMPERATURE", "0.2")
        ),
        summary_provider=provider_setting("SUMMARY_PROVIDER", "deterministic"),
        agent_step_timeout_seconds=float(
            source.get("AGENT_STEP_TIMEOUT_SECONDS", "120")
        ),
        turn_timeout_seconds=float(source.get("TURN_TIMEOUT_SECONDS", "240")),
        paper_judge_provider=provider_setting("PAPER_JUDGE_PROVIDER", "mock"),
        paper_judge_model=source.get(
            "PAPER_JUDGE_MODEL",
            source.get("DEEPSEEK_MODEL", "deepseek-chat"),
        ),
        deepseek_api_key=(
            source.get("DEEPSEEK_API_KEY", "") if real_providers_enabled else ""
        ),
        deepseek_base_url=(
            source.get("DEEPSEEK_BASE_URL", "") if real_providers_enabled else ""
        ),
        deepseek_model=source.get("DEEPSEEK_MODEL", "deepseek-chat"),
    )


config = load_config()
