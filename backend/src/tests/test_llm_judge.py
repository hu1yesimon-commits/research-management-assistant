from services.LlmPaperSelect import LLMJudge
from services.schemas import JudgeResult, PaperId, PaperMetadata
from services.scoreutils import ScoreUtils


def test_judge_without_abstract_uses_scoreutils_for_final_score():
    judge = LLMJudge()
    paper = PaperMetadata(
        paper_id="paper-1",
        source_ids=PaperId(),
        title="Paper without abstract",
        abstract=None,
        source="test",
    )

    result = judge.judge(query="graph reconstruction", paper=paper)

    assert result.decision == "uncertain"
    assert result.final_score == ScoreUtils.calculate_final_score(
        llm_relevance_score=result.llm_relevance_score,
        embedding_relevance_score=result.embedding_relevance_score,
        quality_score=result.quality_score,
        novelty_score=result.novelty_score,
    )


def test_judge_without_abstract_returns_uncertain_manual_review_result():
    judge = LLMJudge()
    paper = PaperMetadata(
        paper_id="paper-1",
        source_ids=PaperId(),
        title="Paper without abstract",
        abstract=None,
        source="test",
    )

    result = judge.judge(query="graph reconstruction", paper=paper)

    assert result.decision == "uncertain"
    assert result.reason == "缺少摘要，无法稳定判断。"
    assert result.llm_relevance_score == 0.3
    assert result.embedding_relevance_score == 0.0
    assert result.quality_score == 0.3
    assert result.novelty_score == 0.5
    assert result.tags == ["missing_abstract", "needs_manual_review"]


def test_mock_provider_scores_depend_on_query_metadata_and_novelty():
    judge = LLMJudge()
    paper = PaperMetadata(
        paper_id="paper-graph-1",
        source_ids=PaperId(doi="10.1000/graph-1", openalex_id="W123"),
        title="Graph Reconstruction with Sparse Priors",
        authors=["Alice", "Bob"],
        abstract="We study graph reconstruction with sparse priors and strong evaluation.",
        venue="NeurIPS",
        citation_count=120,
        published_date="2026-01-10",
        doi="10.1000/graph-1",
        source="openalex",
    )

    result = judge.judge(query="graph reconstruction sparse priors", paper=paper)

    assert result.decision == "accept"
    assert result.llm_relevance_score == 1.0
    assert result.embedding_relevance_score == 1.0
    assert result.quality_score == 0.95
    assert result.novelty_score == 1.0
    assert result.final_score == ScoreUtils.calculate_final_score(
        llm_relevance_score=1.0,
        embedding_relevance_score=1.0,
        quality_score=0.95,
        novelty_score=1.0,
    )
    assert "mock" in result.tags
    assert "high_citation" in result.tags
    assert "top_venue" in result.tags


def test_sort_by_final_score_orders_descending():
    judge = LLMJudge()
    lower = JudgeResult(
        decision="uncertain",
        reason="lower score",
        llm_relevance_score=0.1,
        embedding_relevance_score=0.1,
        quality_score=0.1,
        novelty_score=0.1,
        final_score=0.2,
        tags=[],
    )
    middle = JudgeResult(
        decision="accept",
        reason="middle score",
        llm_relevance_score=0.2,
        embedding_relevance_score=0.2,
        quality_score=0.2,
        novelty_score=0.2,
        final_score=0.5,
        tags=[],
    )
    higher = JudgeResult(
        decision="accept",
        reason="higher score",
        llm_relevance_score=0.3,
        embedding_relevance_score=0.3,
        quality_score=0.3,
        novelty_score=0.3,
        final_score=0.8,
        tags=[],
    )

    assert judge.sort_by_final_score([middle, lower, higher]) == [higher, middle, lower]
