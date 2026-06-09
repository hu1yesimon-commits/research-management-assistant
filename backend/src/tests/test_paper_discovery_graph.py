from graph.builder import build_paper_discovery_graph
from services.memory_store import MemoryStore
from services.query_rewriter import QueryRewriter
from services.schemas import JudgeResult, PaperId, PaperMetadata


class FakeSearchService:
    def search(self, query: str) -> list[PaperMetadata]:
        slug = (
            query.lower()
            .replace(" ", "-")
            .replace("/", "-")
        )
        return [
            PaperMetadata(
                paper_id=f"paper-{slug}",
                source_ids=PaperId(doi=f"10.1000/{slug}"),
                title=f"Paper for {query}",
                authors=["Tester"],
                abstract="Useful abstract.",
                doi=f"10.1000/{slug}",
                source="test",
            )
        ]


class FakeJudge:
    def judge(self, paper: PaperMetadata) -> JudgeResult:
        return JudgeResult(
            decision="accept",
            reason="Relevant",
            llm_relevance_score=0.9,
            embedding_relevance_score=0.8,
            quality_score=0.7,
            novelty_score=1.0,
            final_score=0.85,
            tags=["fake"],
        )

    def sort_by_final_score(self, results: list[JudgeResult]) -> list[JudgeResult]:
        return sorted(results, key=lambda item: item.final_score, reverse=True)


def test_basic_paper_discovery_graph_returns_ranked_candidates_without_persisting(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    graph = build_paper_discovery_graph(
        search_service=FakeSearchService(),
        judge=FakeJudge(),
        memory_store=store,
    )

    result = graph.invoke(
        {
            "mode": "basic",
            "user_query": "graph reconstruction",
            "memory_context": "",
            "rewritten_queries": [],
            "raw_results": [],
            "normalized_papers": [],
            "deduped_papers": [],
            "judge_results": [],
            "ranked_candidates": [],
        }
    )

    assert result["rewritten_queries"] == ["graph reconstruction"]
    assert result["ranked_candidates"][0]["paper"].paper_id == "paper-graph-reconstruction"
    assert store.list_candidate_papers() == []


def test_advanced_graph_uses_memory_context_for_rewritten_queries(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    store.add_experiment_log("model is too heavy", tags=["block"])
    store.add_experiment_log("need better interpretability", tags=["idea"])

    graph = build_paper_discovery_graph(
        search_service=FakeSearchService(),
        judge=FakeJudge(),
        memory_store=store,
        query_rewriter=QueryRewriter(),
    )

    result = graph.invoke(
        {
            "mode": "advanced",
            "user_query": "graph reconstruction",
            "memory_context": "",
            "rewritten_queries": [],
            "raw_results": [],
            "normalized_papers": [],
            "deduped_papers": [],
            "judge_results": [],
            "ranked_candidates": [],
        }
    )

    assert "block: model is too heavy" in result["memory_context"]
    assert "graph reconstruction lightweight" in result["rewritten_queries"]
    assert "graph reconstruction interpretability" in result["rewritten_queries"]
