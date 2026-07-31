from __future__ import annotations

import json
from math import log2
from statistics import fmean
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from evals.schema import (
    AnswerObservation,
    CaseObservation,
    GoldCase,
    GoldDataset,
    ObservationDataset,
    RetrievalObservation,
    RouteObservation,
)

SUPPORTED_SCOPES = {"state", "route", "retrieval", "answer"}


class EvalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SetMetrics(EvalModel):
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float | None
    recall: float | None
    f1: float | None
    exact_match: bool


class ScopeResult(EvalModel):
    scope: str
    hard_gates_passed: bool
    metrics: dict[str, object] = Field(default_factory=dict)
    violations: list[str] = Field(default_factory=list)


class CaseResult(EvalModel):
    case_id: str
    hard_gates_passed: bool
    scopes: list[ScopeResult]


class EvaluationReport(EvalModel):
    dataset: str
    gold_version: str
    gold_status: str
    observation_version: str
    observation_profile: str
    performance_claim_valid: bool
    schema_valid: bool
    hard_gates_passed: bool
    evaluated_case_count: int
    hard_gate_summary: dict[str, int]
    component_scores: dict[str, object]
    cases: list[CaseResult]


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _as_items(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return [value]


def _contains_fact(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, (str, list, dict)):
        return bool(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value != 0
    return bool(value)


def _hashable(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def set_metrics(expected: Iterable[object], observed: Iterable[object]) -> SetMetrics:
    expected_set = {_hashable(value) for value in expected}
    observed_set = {_hashable(value) for value in observed}
    true_positive = len(expected_set & observed_set)
    false_positive = len(observed_set - expected_set)
    false_negative = len(expected_set - observed_set)
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    return SetMetrics(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
        exact_match=expected_set == observed_set,
    )


def evaluate_state(case: GoldCase, observed: dict[str, object]) -> ScopeResult:
    expected = case.expected_state or {}
    field_metrics: dict[str, dict[str, object]] = {}
    false_positive_count = 0
    false_negative_count = 0
    exact_match = True

    for field, expected_value in expected.items():
        observed_value = observed.get(field, [] if isinstance(expected_value, list) else None)
        metrics = set_metrics(_as_items(expected_value), _as_items(observed_value))
        field_metrics[field] = metrics.model_dump(mode="json")
        false_positive_count += metrics.false_positive
        false_negative_count += metrics.false_negative
        exact_match = exact_match and metrics.exact_match

    expected_items = sum(len(_as_items(value)) for value in expected.values())
    matched_items = expected_items - false_negative_count
    critical_field_recall = _ratio(matched_items, expected_items)
    source_attribution_correct = (
        "source_message_ids" not in expected
        or set(observed.get("source_message_ids", []))
        == set(expected["source_message_ids"])
    )
    unadjudicated_fields = sorted(
        field
        for field in set(observed) - set(expected)
        if _contains_fact(observed[field])
    )
    violations = []
    if false_positive_count:
        violations.append(
            f"{false_positive_count} labeled state value(s) were not in Gold"
        )
    if critical_field_recall != 1.0:
        violations.append("critical state field recall is below 100%")
    if not source_attribution_correct:
        violations.append("source message attribution does not match Gold")
    if unadjudicated_fields:
        violations.append(
            "observed non-empty state fields have no Gold label: "
            + ", ".join(unadjudicated_fields)
        )

    return ScopeResult(
        scope="state",
        hard_gates_passed=not violations,
        metrics={
            "labeled_exact_match": exact_match,
            "critical_field_recall": critical_field_recall,
            "labeled_false_positive_count": false_positive_count,
            "labeled_false_negative_count": false_negative_count,
            "source_attribution_correct": source_attribution_correct,
            "unadjudicated_nonempty_field_count": len(unadjudicated_fields),
            "unadjudicated_nonempty_fields": unadjudicated_fields,
            "field_metrics": field_metrics,
        },
        violations=violations,
    )


def evaluate_route(case: GoldCase, observed: RouteObservation) -> ScopeResult:
    route_exact_match = observed.route == case.expected_route
    forbidden_actions = sorted(set(observed.actions) & set(case.forbidden_actions))
    violations = []
    if not route_exact_match:
        violations.append(
            f"expected route {case.expected_route}, observed {observed.route}"
        )
    if forbidden_actions:
        violations.append(
            "forbidden actions observed: " + ", ".join(forbidden_actions)
        )
    return ScopeResult(
        scope="route",
        hard_gates_passed=not violations,
        metrics={
            "route_exact_match": route_exact_match,
            "forbidden_action_violation_count": len(forbidden_actions),
        },
        violations=violations,
    )


def evaluate_retrieval(
    case: GoldCase, observed: RetrievalObservation
) -> ScopeResult:
    fixture = case.retrieval_fixture
    if fixture is None:
        raise ValueError(f"case {case.case_id} has no retrieval fixture")

    retrieved_ids = observed.retrieved_chunk_ids
    relevant_ids = set(fixture.relevant_chunk_ids)
    fixture_ids = {chunk.chunk_id for chunk in fixture.retrieved_chunks}
    unknown_ids = sorted(set(retrieved_ids) - fixture_ids)
    relevant_ranks = [
        index + 1
        for index, chunk_id in enumerate(retrieved_ids)
        if chunk_id in relevant_ids
    ]
    relevant_returned = len(relevant_ranks)
    precision = _ratio(relevant_returned, len(retrieved_ids))
    recall = _ratio(relevant_returned, len(relevant_ids))
    reciprocal_rank = 1 / relevant_ranks[0] if relevant_ranks else None

    ideal_relevant_count = min(len(relevant_ids), len(retrieved_ids))
    dcg = sum(1 / log2(rank + 1) for rank in relevant_ranks)
    ideal_dcg = sum(
        1 / log2(rank + 1) for rank in range(1, ideal_relevant_count + 1)
    )
    ndcg = _ratio(dcg, ideal_dcg)
    evidence_sufficient = relevant_returned > 0
    expected_evidence_sufficient = bool(relevant_ids)
    evidence_sufficiency_correct = (
        evidence_sufficient == expected_evidence_sufficient
    )

    violations = []
    if unknown_ids:
        violations.append(
            "retrieval returned chunk ids outside the fixture: "
            + ", ".join(unknown_ids)
        )
    if not evidence_sufficiency_correct:
        violations.append(
            "retrieval evidence sufficiency does not match the Gold fixture"
        )
    return ScopeResult(
        scope="retrieval",
        hard_gates_passed=not violations,
        metrics={
            "precision_at_k": precision,
            "recall_at_k": recall,
            "recall_applicable": bool(relevant_ids),
            "reciprocal_rank": reciprocal_rank,
            "ndcg_at_k": ndcg,
            "unknown_chunk_id_count": len(unknown_ids),
            "evidence_sufficient": evidence_sufficient,
            "expected_evidence_sufficient": expected_evidence_sufficient,
            "evidence_sufficiency_correct": evidence_sufficiency_correct,
        },
        violations=violations,
    )


def evaluate_answer(
    case: GoldCase, observed: AnswerObservation
) -> ScopeResult:
    contract = case.answer_contract
    if contract is None:
        raise ValueError(f"case {case.case_id} has no answer contract")

    covered_points = set(observed.covered_required_points)
    required_points = set(contract.required_points)
    unrecognized_points = sorted(covered_points - required_points)
    missing_points = sorted(required_points - covered_points)
    detected_forbidden = sorted(
        set(observed.detected_forbidden_claims) & set(contract.forbidden_claims)
    )
    unrecognized_forbidden = sorted(
        set(observed.detected_forbidden_claims) - set(contract.forbidden_claims)
    )
    invalid_citations = sorted(
        set(observed.citation_ids) - set(contract.allowed_citation_ids)
    )
    warning_correct = observed.warned == contract.must_warn
    citation_required = bool(contract.allowed_citation_ids) and bool(covered_points)
    citation_coverage_present = not citation_required or bool(
        observed.citation_ids
    )

    violations = []
    if unrecognized_points:
        violations.append(
            "covered point labels are outside the answer contract: "
            + ", ".join(unrecognized_points)
        )
    if unrecognized_forbidden:
        violations.append(
            "forbidden claim labels are outside the answer contract: "
            + ", ".join(unrecognized_forbidden)
        )
    if detected_forbidden:
        violations.append(
            "forbidden claims detected: " + ", ".join(detected_forbidden)
        )
    if invalid_citations:
        violations.append("invalid citations: " + ", ".join(invalid_citations))
    if missing_points:
        violations.append(
            "required answer points are missing: " + ", ".join(missing_points)
        )
    if not citation_coverage_present:
        violations.append("covered answer points require at least one citation")
    if observed.unsupported_claim_count:
        violations.append(
            f"{observed.unsupported_claim_count} unsupported claim(s) detected"
        )
    if not warning_correct:
        violations.append("warning behavior does not match the answer contract")
    if observed.summary_as_evidence_violation:
        violations.append("session summary or preference was used as evidence")

    coverage = _ratio(len(required_points) - len(missing_points), len(required_points))
    return ScopeResult(
        scope="answer",
        hard_gates_passed=not violations,
        metrics={
            "required_point_coverage": coverage,
            "missing_required_point_count": len(missing_points),
            "citation_coverage_present": citation_coverage_present,
            "invalid_citation_count": len(invalid_citations),
            "forbidden_claim_count": len(detected_forbidden),
            "unsupported_claim_count": observed.unsupported_claim_count,
            "warning_correct": warning_correct,
            "summary_as_evidence_violation": (
                observed.summary_as_evidence_violation
            ),
        },
        violations=violations,
    )


def evaluate_case(case: GoldCase, observation: CaseObservation) -> CaseResult:
    scopes: list[ScopeResult] = []
    observed_by_scope = {
        "state": observation.state,
        "route": observation.route,
        "retrieval": observation.retrieval,
        "answer": observation.answer,
    }
    evaluators = {
        "state": evaluate_state,
        "route": evaluate_route,
        "retrieval": evaluate_retrieval,
        "answer": evaluate_answer,
    }
    for scope, evaluator in evaluators.items():
        if scope not in case.scope:
            continue
        observed = observed_by_scope[scope]
        if observed is None:
            scopes.append(
                ScopeResult(
                    scope=scope,
                    hard_gates_passed=False,
                    violations=[f"missing {scope} observation"],
                )
            )
            continue
        scopes.append(evaluator(case, observed))

    return CaseResult(
        case_id=case.case_id,
        hard_gates_passed=all(scope.hard_gates_passed for scope in scopes),
        scopes=scopes,
    )


def _mean_metric(
    case_results: list[CaseResult], scope_name: str, metric_name: str
) -> float | None:
    values = [
        float(scope.metrics[metric_name])
        for case in case_results
        for scope in case.scopes
        if scope.scope == scope_name
        and isinstance(scope.metrics.get(metric_name), (int, float))
    ]
    return fmean(values) if values else None


def _count_metric(
    case_results: list[CaseResult], scope_name: str, metric_name: str
) -> int:
    return sum(
        int(scope.metrics.get(metric_name, 0))
        for case in case_results
        for scope in case.scopes
        if scope.scope == scope_name
    )


def evaluate_dataset(
    gold: GoldDataset, observations: ObservationDataset
) -> EvaluationReport:
    if observations.dataset != gold.dataset:
        raise ValueError("observation dataset name does not match Gold")
    if observations.version != gold.version:
        raise ValueError("observation version does not match Gold")

    gold_by_id = {case.case_id: case for case in gold.cases}
    unknown_case_ids = sorted(
        {case.case_id for case in observations.cases} - set(gold_by_id)
    )
    if unknown_case_ids:
        raise ValueError(
            "observation contains unknown case ids: " + ", ".join(unknown_case_ids)
        )
    case_results = [
        evaluate_case(gold_by_id[observation.case_id], observation)
        for observation in observations.cases
    ]

    hard_gate_summary = {
        "failed_case_count": sum(
            not result.hard_gates_passed for result in case_results
        ),
        "forbidden_action_violation_count": _count_metric(
            case_results, "route", "forbidden_action_violation_count"
        ),
        "unknown_chunk_id_count": _count_metric(
            case_results, "retrieval", "unknown_chunk_id_count"
        ),
        "invalid_citation_count": _count_metric(
            case_results, "answer", "invalid_citation_count"
        ),
        "unsupported_claim_count": _count_metric(
            case_results, "answer", "unsupported_claim_count"
        ),
    }
    component_scores = {
        "state": {
            "critical_field_recall": _mean_metric(
                case_results, "state", "critical_field_recall"
            ),
            "labeled_exact_match_rate": _mean_metric(
                case_results, "state", "labeled_exact_match"
            ),
        },
        "route": {
            "exact_match_rate": _mean_metric(
                case_results, "route", "route_exact_match"
            )
        },
        "retrieval": {
            "mean_precision_at_k": _mean_metric(
                case_results, "retrieval", "precision_at_k"
            ),
            "mean_recall_at_k": _mean_metric(
                case_results, "retrieval", "recall_at_k"
            ),
            "mean_reciprocal_rank": _mean_metric(
                case_results, "retrieval", "reciprocal_rank"
            ),
            "mean_ndcg_at_k": _mean_metric(
                case_results, "retrieval", "ndcg_at_k"
            ),
        },
        "answer": {
            "mean_required_point_coverage": _mean_metric(
                case_results, "answer", "required_point_coverage"
            ),
            "warning_accuracy": _mean_metric(
                case_results, "answer", "warning_correct"
            ),
        },
    }
    hard_gates_passed = bool(case_results) and all(
        result.hard_gates_passed for result in case_results
    )
    return EvaluationReport(
        dataset=gold.dataset,
        gold_version=gold.version,
        gold_status=gold.status,
        observation_version=observations.version,
        observation_profile=observations.profile,
        performance_claim_valid=(
            observations.profile == "runtime"
            and gold.status == "frozen"
            and bool(observations.cases)
            and {case.case_id for case in observations.cases} == set(gold_by_id)
            and {
                scope for case in gold.cases for scope in case.scope
            }.issubset(SUPPORTED_SCOPES)
        ),
        schema_valid=True,
        hard_gates_passed=hard_gates_passed,
        evaluated_case_count=len(case_results),
        hard_gate_summary=hard_gate_summary,
        component_scores=component_scores,
        cases=case_results,
    )
