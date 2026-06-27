import pytest

from graph.builder import build_paper_discovery_graph
from graph.errors import DiscoveryStageError
from services.memory_store import MemoryStore
from services.query_rewriter import QueryRewriter
from services.schemas import JudgeResult, PaperId, PaperMetadata
from services.scoreutils import ScoreUtils


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
    def __init__(self):
        self.seen_queries: list[str] = []

    def judge(self, query: str, paper: PaperMetadata) -> JudgeResult:
        self.seen_queries.append(query)
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


class PartiallyFailingJudge(FakeJudge):
    def judge(self, query: str, paper: PaperMetadata) -> JudgeResult:
        self.seen_queries.append(query)
        if paper.paper_id == "paper-broken":
            raise RuntimeError("synthetic judge failure for paper-broken")
        return super().judge(query=query, paper=paper)


class FailingQueryRewriter:
    def rewrite(self, mode: str, user_query: str, memory_context: str = "") -> list[str]:
        raise RuntimeError("query rewrite provider unavailable")


class RecordingQueryRewriter:
    def __init__(self):
        self.memory_contexts: list[str] = []

    def rewrite(self, mode: str, user_query: str, memory_context: str = "") -> list[str]:
        self.memory_contexts.append(memory_context)
        return [user_query]


class RankFailingJudge(FakeJudge):
    def sort_by_final_score(self, results: list[JudgeResult]) -> list[JudgeResult]:
        raise RuntimeError("ranking failed")


def test_basic_paper_discovery_graph_returns_ranked_candidates_without_persisting(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    judge = FakeJudge()
    graph = build_paper_discovery_graph(
        search_service=FakeSearchService(),
        judge=judge,
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
    assert judge.seen_queries == ["graph reconstruction"]
    assert store.list_candidate_papers() == []


def test_advanced_graph_uses_memory_context_for_rewritten_queries(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    store.add_experiment_log(
        "legacy model is too heavy and needs better interpretability",
        tags=["legacy"],
    )
    store.add_experiment_log_entry(
        {
            "task": "graph reconstruction",
            "model": "compact GNN",
            "dataset": "defect graph benchmark",
            "metric_problem": "latency is too high",
            "tried_methods": ["pruning"],
            "observation": "need better interpretability while keeping the model light",
            "goal": "find lightweight interpretable graph reconstruction methods",
            "tags": ["lightweight", "interpretability"],
        }
    )

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

    assert "legacy model is too heavy" not in result["memory_context"]
    assert "task=graph reconstruction" in result["memory_context"]
    assert "observation=need better interpretability while keeping the model light" in result["memory_context"]
    assert "graph reconstruction lightweight" in result["rewritten_queries"]
    assert "graph reconstruction interpretability" in result["rewritten_queries"]


def test_paper_discovery_graph_preserves_supplied_memory_snapshot(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    store.add_experiment_log_entry(
        {
            "task": "store context",
            "model": "store model",
            "dataset": "store dataset",
            "metric_problem": "store metric",
            "tried_methods": [],
            "observation": "store observation",
            "goal": "store goal",
            "tags": ["store"],
        }
    )
    supplied_snapshot = "Confirmed semantic memory: supplied by assistant graph"
    rewriter = RecordingQueryRewriter()
    graph = build_paper_discovery_graph(
        search_service=FakeSearchService(),
        judge=FakeJudge(),
        memory_store=store,
        query_rewriter=rewriter,
    )

    result = graph.invoke(
        {
            "mode": "advanced",
            "user_query": "graph reconstruction",
            "memory_context": supplied_snapshot,
            "rewritten_queries": [],
            "raw_results": [],
            "normalized_papers": [],
            "deduped_papers": [],
            "judge_results": [],
            "ranked_candidates": [],
        }
    )

    assert result["memory_context"] == supplied_snapshot
    assert rewriter.memory_contexts == [supplied_snapshot]


def test_paper_discovery_graph_keeps_other_candidates_when_one_judge_fails(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    judge = PartiallyFailingJudge()

    class TwoPaperSearchService:
        def search(self, query: str) -> list[PaperMetadata]:
            return [
                PaperMetadata(
                    paper_id="paper-good",
                    source_ids=PaperId(doi="10.1000/paper-good"),
                    title="Relevant Graph Reconstruction Paper",
                    authors=["Tester"],
                    abstract="Useful abstract.",
                    published_date="2026-02-01",
                    doi="10.1000/paper-good",
                    source="test",
                ),
                PaperMetadata(
                    paper_id="paper-broken",
                    source_ids=PaperId(doi="10.1000/paper-broken"),
                    title="Broken Judge Paper",
                    authors=["Tester"],
                    abstract="Useful abstract.",
                    published_date="2025-02-01",
                    doi="10.1000/paper-broken",
                    source="test",
                ),
            ]

    graph = build_paper_discovery_graph(
        search_service=TwoPaperSearchService(),
        judge=judge,
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

    assert [candidate["paper"].paper_id for candidate in result["ranked_candidates"]] == [
        "paper-good",
        "paper-broken",
    ]

    good_candidate = result["ranked_candidates"][0]
    broken_candidate = result["ranked_candidates"][1]

    assert good_candidate["judgement"].decision == "accept"
    assert good_candidate["judgement"].final_score == 0.85

    assert broken_candidate["judgement"].decision == "uncertain"
    assert "judge failed" in broken_candidate["judgement"].reason.lower()
    assert "synthetic judge failure for paper-broken" in broken_candidate["judgement"].reason
    assert broken_candidate["judgement"].tags == ["judge_failed"]
    assert broken_candidate["judgement"].llm_relevance_score == 0.0
    assert broken_candidate["judgement"].quality_score == 0.0
    assert broken_candidate["judgement"].novelty_score == 0.85
    assert broken_candidate["judgement"].final_score == ScoreUtils.calculate_final_score(
        llm_relevance_score=0.0,
        embedding_relevance_score=0.0,
        quality_score=0.0,
        novelty_score=0.85,
    )


def test_paper_discovery_graph_classifies_query_rewrite_failure(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    graph = build_paper_discovery_graph(
        search_service=FakeSearchService(),
        judge=FakeJudge(),
        memory_store=store,
        query_rewriter=FailingQueryRewriter(),
    )

    with pytest.raises(DiscoveryStageError) as exc_info:
        graph.invoke(
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

    assert exc_info.value.stage == "query_rewrite"
    assert exc_info.value.detail == "query rewrite provider unavailable"
    assert exc_info.value.recoverable is True


def test_paper_discovery_graph_classifies_rank_failure(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    graph = build_paper_discovery_graph(
        search_service=FakeSearchService(),
        judge=RankFailingJudge(),
        memory_store=store,
    )

    with pytest.raises(DiscoveryStageError) as exc_info:
        graph.invoke(
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

    assert exc_info.value.stage == "rank"
    assert exc_info.value.detail == "ranking failed"
    assert exc_info.value.recoverable is False
