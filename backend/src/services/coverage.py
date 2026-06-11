from __future__ import annotations

import re


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "should",
    "the",
    "to",
    "with",
}


def normalize_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {token for token in tokens if len(token) >= 2 and token not in STOPWORDS}


def overlap_score(query: str, context: str) -> float:
    query_tokens = normalize_tokens(query)
    if not query_tokens:
        return 0.0
    context_tokens = normalize_tokens(context)
    score = len(query_tokens & context_tokens) / len(query_tokens)
    return _clamp(score)


def calculate_coverage_score(
    query: str,
    semantic_memory_text: str,
    recent_log_text: str,
    has_knowledge_sources: bool,
) -> tuple[float, str]:
    semantic_score = overlap_score(query, semantic_memory_text)
    recent_log_score = overlap_score(query, recent_log_text)
    knowledge_score = 1.0 if has_knowledge_sources else 0.0
    score = _clamp(
        (0.4 * semantic_score)
        + (0.3 * recent_log_score)
        + (0.3 * knowledge_score)
    )
    reason = (
        f"coverage heuristic: semantic={semantic_score:.2f}, "
        f"recent_logs={recent_log_score:.2f}, "
        f"knowledge={knowledge_score:.2f}"
    )
    return score, reason


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
