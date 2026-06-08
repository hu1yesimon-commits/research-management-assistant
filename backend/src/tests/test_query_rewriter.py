from services.query_rewriter import QueryRewriter


def test_basic_mode_returns_original_query():
    rewriter = QueryRewriter()

    queries = rewriter.rewrite(
        mode="basic",
        user_query="graph reconstruction",
        memory_context="old logs",
    )

    assert queries == ["graph reconstruction"]


def test_advanced_mode_adds_research_direction_queries():
    rewriter = QueryRewriter()

    queries = rewriter.rewrite(
        mode="advanced",
        user_query="graph reconstruction",
        memory_context="block: model is too heavy; idea: improve interpretability",
    )

    assert "graph reconstruction lightweight" in queries
    assert "graph reconstruction interpretability" in queries


def test_advanced_mode_falls_back_to_default_directions_without_signals():
    rewriter = QueryRewriter()

    queries = rewriter.rewrite(
        mode="advanced",
        user_query="graph reconstruction",
        memory_context="notes: need better references soon",
    )

    assert queries == [
        "graph reconstruction",
        "graph reconstruction survey",
        "graph reconstruction recent methods",
    ]
