from services.coverage import calculate_coverage_score, normalize_tokens, overlap_score


def test_normalize_tokens_lowercases_splits_and_removes_stopwords():
    assert normalize_tokens("How should I improve Graph-Reconstruction, with GNN?") == {
        "improve",
        "graph",
        "reconstruction",
        "gnn",
    }


def test_overlap_score_uses_query_token_denominator():
    score = overlap_score("graph reconstruction precision", "confirmed graph reconstruction memory")

    assert score == 2 / 3


def test_calculate_coverage_score_combines_memory_logs_and_knowledge_signal():
    score, reason = calculate_coverage_score(
        query="graph reconstruction precision",
        semantic_memory_text="User focuses on graph reconstruction.",
        recent_log_text="Recent episodic memory mentions precision collapse.",
        has_knowledge_sources=True,
    )

    assert round(score, 2) == 0.67
    assert "semantic=0.67" in reason
    assert "recent_logs=0.33" in reason
    assert "knowledge=1.00" in reason


def test_calculate_coverage_score_returns_zero_for_empty_signals():
    score, reason = calculate_coverage_score(
        query="unknown topic",
        semantic_memory_text="",
        recent_log_text="",
        has_knowledge_sources=False,
    )

    assert score == 0.0
    assert "knowledge=0.00" in reason
