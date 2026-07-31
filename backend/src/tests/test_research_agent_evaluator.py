import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.__main__ import main
from evals.evaluator import (
    evaluate_answer,
    evaluate_dataset,
    evaluate_retrieval,
    evaluate_route,
    evaluate_state,
)
from evals.schema import (
    AnswerObservation,
    GoldDataset,
    ObservationDataset,
    RetrievalObservation,
    RouteObservation,
)


ROOT = Path(__file__).resolve().parents[3]
GOLD_PATH = (
    ROOT / "docs" / "superpowers" / "evals" / "research-agent-gold-v0.json"
)
PROBE_PATH = (
    ROOT
    / "backend"
    / "src"
    / "evals"
    / "fixtures"
    / "research-agent-contract-probe-v0.json"
)


@pytest.fixture
def gold():
    return GoldDataset.from_path(GOLD_PATH)


def test_gold_schema_loads_current_draft(gold):
    assert gold.dataset == "research-agent-gold"
    assert gold.version == "0.2.0-draft"
    assert gold.status == "human_review_required"
    assert len(gold.cases) == 12


def test_gold_schema_rejects_citations_outside_retrieval_fixture():
    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["answer_contract"]["allowed_citation_ids"].append(
        "chunk-not-in-fixture"
    )

    with pytest.raises(ValidationError, match="allowed citations"):
        GoldDataset.model_validate(payload)


def test_gold_schema_rejects_irrelevant_citation_as_allowed():
    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["answer_contract"]["allowed_citation_ids"] = [
        "chunk-augmentation-noise-1"
    ]

    with pytest.raises(
        ValidationError,
        match="allowed citations must be relevant",
    ):
        GoldDataset.model_validate(payload)


def test_gold_schema_rejects_empty_or_unreviewed_contract_shapes():
    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    payload["status"] = "review_complete_typo"

    with pytest.raises(ValidationError):
        GoldDataset.model_validate(payload)

    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    payload["cases"] = []
    with pytest.raises(ValidationError):
        GoldDataset.model_validate(payload)

    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["expected_state"] = {}
    with pytest.raises(ValidationError, match="non-empty expected_state"):
        GoldDataset.model_validate(payload)


def test_observation_schema_rejects_wrong_state_value_shape():
    payload = json.loads(PROBE_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["state"]["intent"] = ["experiment_improvement"]

    with pytest.raises(ValidationError, match="intent must be a string"):
        ObservationDataset.model_validate(payload)


def test_gold_schema_rejects_case_without_deterministic_scope():
    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["scope"] = ["ablation"]

    with pytest.raises(
        ValidationError,
        match="at least one deterministic evaluator scope",
    ):
        GoldDataset.model_validate(payload)


def test_contract_probe_exercises_all_deterministic_scopes(gold):
    observations = ObservationDataset.from_path(PROBE_PATH)

    report = evaluate_dataset(gold, observations)

    assert report.hard_gates_passed is True
    assert report.performance_claim_valid is False
    assert report.evaluated_case_count == 1
    assert report.component_scores["state"]["critical_field_recall"] == 1.0
    assert report.component_scores["state"]["labeled_exact_match_rate"] == 1.0
    assert report.component_scores["route"]["exact_match_rate"] == 1.0
    assert report.component_scores["retrieval"]["mean_precision_at_k"] == 0.5
    assert report.component_scores["retrieval"]["mean_recall_at_k"] == 1.0
    assert report.component_scores["answer"]["mean_required_point_coverage"] == 1.0


def test_negative_retrieval_case_reports_non_applicable_recall(gold):
    case = next(
        case
        for case in gold.cases
        if case.case_id == "exp-sensor-drift-fallback-002"
    )

    result = evaluate_retrieval(
        case,
        RetrievalObservation(
            retrieved_chunk_ids=["chunk-same-device-only-1"]
        ),
    )

    assert result.hard_gates_passed is True
    assert result.metrics["precision_at_k"] == 0.0
    assert result.metrics["recall_at_k"] is None
    assert result.metrics["recall_applicable"] is False
    assert result.metrics["evidence_sufficiency_correct"] is True


def test_positive_retrieval_without_relevant_evidence_fails(gold):
    case = gold.cases[0]

    result = evaluate_retrieval(
        case,
        RetrievalObservation(
            retrieved_chunk_ids=["chunk-augmentation-noise-1"]
        ),
    )

    assert result.hard_gates_passed is False
    assert result.metrics["evidence_sufficiency_correct"] is False


def test_route_forbidden_action_is_a_hard_gate(gold):
    case = gold.cases[0]

    result = evaluate_route(
        case,
        RouteObservation(
            route="experiment_improvement",
            actions=["accept_candidate"],
        ),
    )

    assert result.hard_gates_passed is False
    assert result.metrics["forbidden_action_violation_count"] == 1


def test_answer_invalid_citation_is_a_hard_gate(gold):
    case = gold.cases[0]

    result = evaluate_answer(
        case,
        AnswerObservation(
            covered_required_points=case.answer_contract.required_points,
            citation_ids=["chunk-not-allowed"],
            warned=False,
        ),
    )

    assert result.hard_gates_passed is False
    assert result.metrics["invalid_citation_count"] == 1


def test_answer_missing_points_and_citations_fails(gold):
    case = gold.cases[0]

    result = evaluate_answer(
        case,
        AnswerObservation(
            covered_required_points=[],
            citation_ids=[],
            warned=False,
        ),
    )

    assert result.hard_gates_passed is False
    assert result.metrics["missing_required_point_count"] == 2


def test_unadjudicated_nonempty_state_fact_fails(gold):
    case = gold.cases[0]
    observed = dict(case.expected_state)
    observed["research_goal"] = "hallucinated goal"

    result = evaluate_state(case, observed)

    assert result.hard_gates_passed is False
    assert result.metrics["unadjudicated_nonempty_field_count"] == 1


def test_missing_scoped_observation_fails_case(gold):
    observations = ObservationDataset.model_validate(
        {
            "dataset": gold.dataset,
            "version": gold.version,
            "profile": "runtime",
            "cases": [
                {
                    "case_id": "exp-supported-precision-001",
                    "route": {
                        "route": "experiment_improvement",
                        "actions": [],
                    },
                }
            ],
        }
    )

    report = evaluate_dataset(gold, observations)

    assert report.hard_gates_passed is False
    assert report.hard_gate_summary["failed_case_count"] == 1
    assert {
        scope.scope
        for scope in report.cases[0].scopes
        if not scope.hard_gates_passed
    } == {"state", "retrieval", "answer"}


def test_cli_writes_machine_readable_report(tmp_path):
    output_path = tmp_path / "report.json"

    exit_code = main(
        [
            "--gold",
            str(GOLD_PATH),
            "--observed",
            str(PROBE_PATH),
            "--output",
            str(output_path),
        ]
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["hard_gates_passed"] is True
    assert report["observation_profile"] == "contract_probe"
    assert report["performance_claim_valid"] is False


def test_cli_returns_nonzero_when_a_hard_gate_fails(tmp_path):
    observed_payload = json.loads(PROBE_PATH.read_text(encoding="utf-8"))
    observed_payload["cases"][0]["answer"]["citation_ids"] = [
        "chunk-not-allowed"
    ]
    observed_path = tmp_path / "failing-observed.json"
    observed_path.write_text(
        json.dumps(observed_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--gold",
            str(GOLD_PATH),
            "--observed",
            str(observed_path),
        ]
    )

    assert exit_code == 1
