from dotenv import load_dotenv
load_dotenv()

import os
from dataclasses import dataclass


@dataclass
class Config:
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
    answer_model: str = "gpt-4.1-mini"
    answer_temperature: float = 0.0
    idea_provider: str = "deterministic"
    idea_model: str = "deepseek-chat"
    idea_temperature: float = 0.0
    paper_judge_provider: str = "mock"
    paper_judge_model: str = "deepseek-chat"
    deepseek_api_key: str = ""
    deepseek_base_url: str = ""
    deepseek_model: str = "deepseek-chat"

config = Config(
    arxiv_max_results=int(os.getenv("ARXIV_MAX_RESULTS", "10")),
    arxiv_rate_limit=float(os.getenv("ARXIV_RATE_LIMIT_SECONDS", "3.0")),
    arxiv_sort_by=os.getenv("ARXIV_SORT_BY", "submittedDate"),
    arxiv_sort_order=os.getenv("ARXIV_SORT_ORDER", "descending"),

    openalex_api_key=os.getenv("OPENALEX_API_KEY", ""),
    openalex_mailto=os.getenv("OPENALEX_MAILTO", ""),
    openalex_rate_limit=float(os.getenv("OPENALEX_RATE_LIMIT_SECONDS", "1.0")),
    openalex_max_results=int(os.getenv("OPENALEX_MAX_RESULTS", "10")),

    semantic_scholar_api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY", ""),
    semantic_scholar_rate_limit=float(os.getenv("SEMANTIC_SCHOLAR_RATE_LIMIT_SECONDS", "1.0")),

    database_path=os.getenv("DATABASE_PATH", "backend/data/research_memory.sqlite3"),
    pdf_upload_dir=os.getenv("PDF_UPLOAD_DIR", "backend/data/uploads"),
    vector_store_dir=os.getenv("VECTOR_STORE_DIR", "backend/data/vector_store"),
    vector_backend=os.getenv("VECTOR_BACKEND", "fake"),
    chroma_persist_dir=os.getenv("CHROMA_PERSIST_DIR", "backend/data/vector_store/chroma"),
    chroma_collection_name=os.getenv("CHROMA_COLLECTION_NAME", "research_chunks"),
    embedding_provider=os.getenv("EMBEDDING_PROVIDER", "fake"),
    bge_m3_model_name=os.getenv("BGE_M3_MODEL_NAME", "BAAI/bge-m3"),
    answer_provider=os.getenv("ANSWER_PROVIDER", "deterministic"),
    answer_model=os.getenv("ANSWER_MODEL", "gpt-4.1-mini"),
    answer_temperature=float(os.getenv("ANSWER_TEMPERATURE", "0")),
    idea_provider=os.getenv("IDEA_PROVIDER", "deterministic"),
    idea_model=os.getenv("IDEA_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-chat")),
    idea_temperature=float(os.getenv("IDEA_TEMPERATURE", "0")),
    paper_judge_provider=os.getenv("PAPER_JUDGE_PROVIDER", "mock"),
    paper_judge_model=os.getenv("PAPER_JUDGE_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-chat")),
    deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
    deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", ""),
    deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),

)
