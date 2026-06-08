from typing import Literal, TypedDict

from services.schemas import JudgeResult, PaperMetadata


class RankedCandidate(TypedDict):
    paper: PaperMetadata
    judgement: JudgeResult


class PaperDiscoveryState(TypedDict):
    mode: Literal["basic", "advanced"]
    user_query: str
    memory_context: str
    rewritten_queries: list[str]
    raw_results: list[PaperMetadata]
    normalized_papers: list[PaperMetadata]
    deduped_papers: list[PaperMetadata]
    judge_results: list[JudgeResult]
    ranked_candidates: list[RankedCandidate]


class PaperSelectState(TypedDict):
    papers: list[PaperMetadata]
    judge_results: list[JudgeResult]
