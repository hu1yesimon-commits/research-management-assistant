from services.schemas import PaperId, PaperMetadata
from services.scoreutils import ScoreUtils


def test_calculate_final_score_applies_each_weight_coefficient():
    assert (
        ScoreUtils.calculate_final_score(
            llm_relevance_score=1.0,
            embedding_relevance_score=0.0,
            quality_score=0.0,
            novelty_score=0.0,
        )
        == 0.4
    )
    assert (
        ScoreUtils.calculate_final_score(
            llm_relevance_score=0.0,
            embedding_relevance_score=1.0,
            quality_score=0.0,
            novelty_score=0.0,
        )
        == 0.15
    )
    assert (
        ScoreUtils.calculate_final_score(
            llm_relevance_score=0.0,
            embedding_relevance_score=0.0,
            quality_score=1.0,
            novelty_score=0.0,
        )
        == 0.25
    )
    assert (
        ScoreUtils.calculate_final_score(
            llm_relevance_score=0.0,
            embedding_relevance_score=0.0,
            quality_score=0.0,
            novelty_score=1.0,
        )
        == 0.2
    )


def test_calculate_final_score_uses_expected_weights():
    score = ScoreUtils.calculate_final_score(
        llm_relevance_score=0.9,
        embedding_relevance_score=0.8,
        quality_score=0.6,
        novelty_score=0.5,
    )

    assert score == 0.73


def test_calculate_embedding_relevance_score_uses_query_title_abstract_overlap():
    paper = PaperMetadata(
        paper_id="paper-overlap",
        source_ids=PaperId(),
        title="Graph Reconstruction with Sparse Priors",
        abstract="This paper studies graph reconstruction and sparse signals.",
        source="test",
    )

    score = ScoreUtils.calculate_embedding_relevance_score(
        query="graph reconstruction sparse priors",
        paper=paper,
    )

    assert score == 1.0


def test_calculate_embedding_relevance_score_returns_zero_when_query_has_no_overlap():
    paper = PaperMetadata(
        paper_id="paper-no-overlap",
        source_ids=PaperId(),
        title="Protein Folding by Diffusion",
        abstract="We model protein conformations with diffusion models.",
        source="test",
    )

    score = ScoreUtils.calculate_embedding_relevance_score(
        query="graph reconstruction sparse priors",
        paper=paper,
    )

    assert score == 0.0


def test_calculate_novelty_score_defaults_when_date_missing():
    paper = PaperMetadata(
        paper_id="paper-1",
        source_ids=PaperId(),
        title="Test paper",
        source="test",
        published_date=None,
    )

    assert ScoreUtils.calculate_novelty_score(paper, current_year=2026) == 0.5


def test_calculate_novelty_score_decays_by_publication_age():
    current_year_paper = PaperMetadata(
        paper_id="paper-current",
        source_ids=PaperId(),
        title="Current paper",
        source="test",
        published_date="2026-02-01",
    )
    one_year_old_paper = PaperMetadata(
        paper_id="paper-one-year",
        source_ids=PaperId(),
        title="One year old paper",
        source="test",
        published_date="2025-02-01",
    )
    older_paper = PaperMetadata(
        paper_id="paper-older",
        source_ids=PaperId(),
        title="Older paper",
        source="test",
        published_date="2016-02-01",
    )

    assert ScoreUtils.calculate_novelty_score(current_year_paper, current_year=2026) == 1.0
    assert ScoreUtils.calculate_novelty_score(one_year_old_paper, current_year=2026) == 0.85
    assert ScoreUtils.calculate_novelty_score(older_paper, current_year=2026) == 0.1
