from services.paper_search import PaperSearchService
from services.adapters.openalex_adapter import OpenAlexAdapter
from services.schemas import PaperId, PaperMetadata


class FakeArxivEmpty:
    last_status = {"status": "network_error", "source": "arxiv", "error": "dns"}

    def search(self, query: str) -> list[PaperMetadata]:
        return []


class FakeArxivOne:
    last_status = {"status": "ok", "source": "arxiv", "result_count": 1}

    def search(self, query: str) -> list[PaperMetadata]:
        return [
            PaperMetadata(
                paper_id="arxiv_1",
                source_ids=PaperId(arxiv_id="1234.5678"),
                title="Graph Reconstruction via Example",
                authors=["Tester"],
                source="arxiv",
                raw={},
            )
        ]


class FakeOpenAlexMissing:
    last_status = {"status": "no_match", "source": "openalex", "query_title": "Graph Reconstruction via Example"}

    def enrich_by_title(self, title: str) -> dict | None:
        return None


class FakeOpenAlexPatch:
    last_status = {
        "status": "ok",
        "source": "openalex",
        "query_title": "Graph Reconstruction via Example",
        "matched_title": "Graph Reconstruction via Example",
        "match_type": "exact_normalized",
    }

    def enrich_by_title(self, title: str) -> dict | None:
        return {
            "doi": "10.1000/example",
            "venue": "Example Journal",
            "venue_type": "journal",
            "citation_count": 42,
            "openalex_id": "W123",
            "match_type": "exact_normalized",
            "match_confidence": 1.0,
            "matched_title": title,
            "_debug": {
                "query_title": title,
                "matched_title": title,
                "match_type": "exact_normalized",
            },
            "_raw": {"id": "https://openalex.org/W123"},
        }


class FakeOpenAlexTopResultPatch:
    last_status = {
        "status": "ok",
        "source": "openalex",
        "query_title": "Graph Reconstruction via Example",
        "matched_title": "The Reconstruction of Graphs",
        "match_type": "search_top_result",
    }

    def enrich_by_title(self, title: str) -> dict | None:
        return {
            "doi": "10.1000/wrong-match",
            "venue": "Different Journal",
            "venue_type": "journal",
            "citation_count": 7,
            "openalex_id": "W999",
            "match_type": "search_top_result",
            "match_confidence": 0.5,
            "matched_title": "The Reconstruction of Graphs",
            "_debug": {
                "query_title": title,
                "matched_title": "The Reconstruction of Graphs",
                "match_type": "search_top_result",
            },
            "_raw": {"id": "https://openalex.org/W999", "display_name": "The Reconstruction of Graphs"},
        }


def test_search_logs_arxiv_failure_reason(capsys):
    service = PaperSearchService(arxiv=FakeArxivEmpty(), openalex=FakeOpenAlexMissing())

    papers = service.search("graph reconstruction")

    assert papers == []
    captured = capsys.readouterr()
    assert "arXiv returned 0 papers" in captured.out
    assert "network_error" in captured.out


def test_search_logs_openalex_skip_reason(capsys):
    service = PaperSearchService(arxiv=FakeArxivOne(), openalex=FakeOpenAlexMissing())

    papers = service.search("graph reconstruction")

    assert len(papers) == 1
    captured = capsys.readouterr()
    assert "OpenAlex enrichment skipped" in captured.out
    assert "no_match" in captured.out


def test_merge_persists_openalex_debug_metadata():
    service = PaperSearchService(arxiv=FakeArxivOne(), openalex=FakeOpenAlexPatch())

    papers = service.search("graph reconstruction")

    assert len(papers) == 1
    paper = papers[0]
    assert paper.doi == "10.1000/example"
    assert paper.source_ids.openalex_id == "W123"
    assert paper.raw["openalex"]["id"] == "https://openalex.org/W123"
    assert paper.raw["openalex_debug"]["match_type"] == "exact_normalized"


def test_search_top_result_does_not_merge_core_fields():
    service = PaperSearchService(arxiv=FakeArxivOne(), openalex=FakeOpenAlexTopResultPatch())

    papers = service.search("graph reconstruction")

    assert len(papers) == 1
    paper = papers[0]
    assert paper.doi is None
    assert paper.citation_count is None
    assert paper.venue is None
    assert paper.venue_type is None
    assert paper.source_ids.openalex_id is None


def test_search_top_result_is_saved_as_openalex_candidate():
    service = PaperSearchService(arxiv=FakeArxivOne(), openalex=FakeOpenAlexTopResultPatch())

    papers = service.search("graph reconstruction")

    paper = papers[0]
    assert paper.raw["openalex_candidate"]["id"] == "https://openalex.org/W999"
    assert paper.raw["openalex_debug"]["match_type"] == "search_top_result"
    assert paper.raw["openalex_debug"]["matched_title"] == "The Reconstruction of Graphs"


def test_openalex_normalize_title_handles_case_whitespace_and_basic_punctuation():
    adapter = OpenAlexAdapter()

    left = adapter._normalize_title("  The Reconstruction of Graphs:  ")
    right = adapter._normalize_title("the   reconstruction of graphs")
    third = adapter._normalize_title("The Reconstruction of Graphs.")

    assert left == "the reconstruction of graphs"
    assert right == "the reconstruction of graphs"
    assert third == "the reconstruction of graphs"
