from graph.builder import build_paper_select_graph
from services.schemas import PaperId, PaperMetadata


def test_build_paper_select_graph_runs_end_to_end():
    graph = build_paper_select_graph()

    paper_without_abstract = PaperMetadata(
        paper_id="paper-1",
        source_ids=PaperId(),
        title="Paper without abstract",
        abstract=None,
        source="test",
    )
    paper_with_abstract = PaperMetadata(
        paper_id="paper-2",
        source_ids=PaperId(),
        title="Paper with abstract",
        abstract="Useful abstract",
        source="test",
    )

    result = graph.invoke(
        {
            "papers": [paper_without_abstract, paper_with_abstract],
            "judge_results": [],
            "user_query": "useful abstract",
        }
    )

    assert [item.paper_id for item in result["papers"]] == ["paper-1", "paper-2"]
    assert [item.decision for item in result["judge_results"]] == ["uncertain", "uncertain"]


def test_build_paper_select_graph_returns_ranked_judge_results_for_fake_papers():
    graph = build_paper_select_graph()

    lower_ranked_paper = PaperMetadata(
        paper_id="paper-1",
        source_ids=PaperId(),
        title="Paper without abstract",
        abstract=None,
        source="test",
    )
    higher_ranked_paper = PaperMetadata(
        paper_id="paper-2",
        source_ids=PaperId(),
        title="Paper with abstract",
        abstract="Useful abstract",
        source="test",
    )

    result = graph.invoke(
        {
            "papers": [lower_ranked_paper, higher_ranked_paper],
            "judge_results": [],
            "user_query": "useful abstract",
        }
    )

    assert [item.decision for item in result["judge_results"]] == ["uncertain", "uncertain"]
    assert [item.final_score for item in result["judge_results"]] == [0.725, 0.295]


def test_build_paper_select_graph_filters_current_batch_weak_title_duplicates():
    graph = build_paper_select_graph()

    first_duplicate = PaperMetadata(
        paper_id="paper-1",
        source_ids=PaperId(),
        title="Graph Neural Networks",
        abstract="Useful abstract",
        source="test",
    )
    second_duplicate = PaperMetadata(
        paper_id="paper-2",
        source_ids=PaperId(),
        title="  graph   neural networks ",
        abstract="Another abstract",
        source="test",
    )
    unique_paper = PaperMetadata(
        paper_id="paper-3",
        source_ids=PaperId(),
        title="Graph Transformers",
        abstract=None,
        source="test",
    )

    result = graph.invoke(
        {
            "papers": [first_duplicate, second_duplicate, unique_paper],
            "judge_results": [],
            "user_query": "graph neural networks",
        }
    )

    assert [item.paper_id for item in result["papers"]] == ["paper-1", "paper-2", "paper-3"]
    assert [item.decision for item in result["judge_results"]] == ["uncertain", "uncertain"]
    assert [item.final_score for item in result["judge_results"]] == [0.725, 0.295]
