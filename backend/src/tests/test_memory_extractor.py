from services.memory_extractor import MemoryExtractor, normalize_memory_object


def make_log(log_id: int, method: str = "focal loss") -> dict:
    return {
        "id": log_id,
        "task": "defect classification",
        "model": "1D-CNN",
        "dataset": "bearing fault dataset",
        "metric_problem": "minority PRAUC is low",
        "tried_methods": [method],
        "observation": "recall improves but precision collapses",
        "goal": "improve PRAUC without making model too heavy",
        "tags": ["imbalanced-learning", "lightweight"],
        "created_at": "2026-06-10T00:00:00+00:00",
    }


def test_normalize_memory_object_merges_hyphen_and_spaces():
    assert normalize_memory_object(" Focal-Loss  ") == "focal loss"


def test_extractor_generates_semantic_proposal_after_three_occurrences():
    extractor = MemoryExtractor()

    candidates = extractor.extract_semantic_proposals(
        [make_log(1, "focal-loss"), make_log(2, "focal loss"), make_log(3, "FOCAL   LOSS")]
    )

    focal = [
        candidate
        for candidate in candidates
        if candidate["category"] == "experiment_target" and candidate["object"] == "focal loss"
    ]
    assert len(focal) == 1
    assert focal[0]["candidate_type"] == "semantic_proposal"
    assert focal[0]["predicate"] == "uses_object"
    assert focal[0]["evidence_count"] == 3
    assert focal[0]["source_log_ids"] == [1, 2, 3]


def test_extractor_does_not_propose_one_off_fact():
    extractor = MemoryExtractor()

    candidates = extractor.extract_semantic_proposals([make_log(1)])

    assert candidates == []
