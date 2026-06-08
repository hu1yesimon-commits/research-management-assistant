from services.deduplicator import DeDuplicator
from services.schemas import PaperId, PaperMetadata


def test_normalize_doi_strips_whitespace_and_lowercases():
    assert DeDuplicator._normalize_doi(" 10.1234/ABC-Def ") == "10.1234/abc-def"


def test_normalize_doi_returns_none_for_empty_values():
    assert DeDuplicator._normalize_doi(None) is None
    assert DeDuplicator._normalize_doi("") is None


def test_normalize_doi_removes_common_prefixes():
    assert DeDuplicator._normalize_doi("https://doi.org/10.1234/ABC") == "10.1234/abc"
    assert DeDuplicator._normalize_doi("doi:10.1234/ABC") == "10.1234/abc"


def test_normalize_title_collapses_whitespace_and_lowercases():
    assert DeDuplicator._normalize_title("  Graph   Neural Networks  ") == "graph neural networks"


def test_dedup_filters_current_batch_duplicates_by_normalized_title():
    deduplicator = DeDuplicator(storage_path="/private/tmp/nonexistent-known-papers.json")
    papers = [
        PaperMetadata(
            paper_id="paper-1",
            source_ids=PaperId(),
            title="Graph Neural Networks",
            doi=None,
            source="test",
        ),
        PaperMetadata(
            paper_id="paper-2",
            source_ids=PaperId(),
            title="  graph   neural networks ",
            doi=None,
            source="test",
        ),
        PaperMetadata(
            paper_id="paper-3",
            source_ids=PaperId(),
            title="Graph Transformers",
            doi=None,
            source="test",
        ),
    ]

    result = deduplicator.dedup(papers)

    assert [paper.paper_id for paper in result] == ["paper-1", "paper-3"]
