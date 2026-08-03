from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DeterministicScope = Literal["state", "route", "retrieval", "answer"]
Scope = Literal["state", "route", "retrieval", "answer", "ablation", "e2e"]
Route = Literal[
    "direct_reply",
    "clarify",
    "discovery",
    "knowledge_qa",
    "discovery_with_knowledge",
    "experiment_improvement",
    "experiment_discovery_fallback",
    "memory_command",
]

STATE_FIELDS = {
    "intent",
    "research_goal",
    "current_hypothesis",
    "attempted_methods",
    "observed_results",
    "decisions",
    "unresolved_problems",
    "constraints",
    "preference_candidates",
    "source_message_ids",
    "superseded_decisions",
    "updated_through_message_id",
}
STATE_STRING_FIELDS = {"intent", "research_goal", "current_hypothesis"}
STATE_STRING_LIST_FIELDS = STATE_FIELDS - STATE_STRING_FIELDS - {
    "source_message_ids",
    "updated_through_message_id",
}


def _validate_state_values(state: dict[str, object], label: str) -> None:
    unknown_fields = set(state) - STATE_FIELDS
    if unknown_fields:
        raise ValueError(
            f"unknown {label} state fields: " + ", ".join(sorted(unknown_fields))
        )
    for field_name, value in state.items():
        if field_name in STATE_STRING_FIELDS and not isinstance(value, str):
            raise ValueError(f"{label} state field {field_name} must be a string")
        if field_name in STATE_STRING_LIST_FIELDS:
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise ValueError(
                    f"{label} state field {field_name} must be a string list"
                )
            if len(value) != len(set(value)):
                raise ValueError(
                    f"{label} state field {field_name} values must be unique"
                )
        if field_name == "source_message_ids":
            if not isinstance(value, list) or not all(
                isinstance(item, int) and not isinstance(item, bool)
                for item in value
            ):
                raise ValueError(
                    f"{label} state field source_message_ids must be an integer list"
                )
            if len(value) != len(set(value)):
                raise ValueError(
                    f"{label} state field source_message_ids must be unique"
                )
        if field_name == "updated_through_message_id" and (
            not isinstance(value, int) or isinstance(value, bool)
        ):
            raise ValueError(
                f"{label} state field updated_through_message_id must be an integer"
            )


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrimaryDomain(StrictModel):
    name: str
    tasks: list[str]
    repository_name_is_domain_signal: bool


class Message(StrictModel):
    id: int
    role: Literal["system", "user", "assistant"]
    text: str


class SessionSummary(StrictModel):
    research_goal: str
    attempted_methods: list[str]
    observed_results: list[str]
    decisions: list[str]
    unresolved_problems: list[str]
    current_constraints: list[str]
    updated_through_message_id: int


class RetrievedChunk(StrictModel):
    chunk_id: str
    text: str


class RetrievalFixture(StrictModel):
    retrieved_chunks: list[RetrievedChunk]
    relevant_chunk_ids: list[str]
    discovery_candidate_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_chunk_ids(self) -> RetrievalFixture:
        chunk_ids = [chunk.chunk_id for chunk in self.retrieved_chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("retrieval fixture chunk ids must be unique")
        unknown_relevant = set(self.relevant_chunk_ids) - set(chunk_ids)
        if unknown_relevant:
            raise ValueError(
                "relevant chunk ids must exist in retrieved chunks: "
                + ", ".join(sorted(unknown_relevant))
            )
        return self


class AnswerContract(StrictModel):
    required_points: list[str]
    forbidden_claims: list[str]
    allowed_citation_ids: list[str]
    must_warn: bool
    summary_as_evidence_violation: bool | None = None


class GoldCase(StrictModel):
    case_id: str
    scope: list[Scope] = Field(min_length=1)
    messages: list[Message]
    session_summary: SessionSummary
    preference_memory: list[str]
    expected_state: dict[str, object] | None = None
    expected_route: Route
    retrieval_fixture: RetrievalFixture | None = None
    answer_contract: AnswerContract | None = None
    required_clarification_fields: list[str] = Field(default_factory=list)
    forbidden_actions: list[str]
    expected_final_outcome: dict[str, object] | None = None

    @model_validator(mode="after")
    def validate_scoped_labels(self) -> GoldCase:
        if len(self.scope) != len(set(self.scope)):
            raise ValueError("case scopes must be unique")
        if not set(self.scope).intersection({"state", "route", "retrieval", "answer"}):
            raise ValueError(
                "case must include at least one deterministic evaluator scope"
            )
        if "state" in self.scope:
            if self.expected_state is None:
                raise ValueError("state scope requires expected_state")
            if not self.expected_state:
                raise ValueError("state scope requires non-empty expected_state")
            _validate_state_values(self.expected_state, "expected")
        if "retrieval" in self.scope and self.retrieval_fixture is None:
            raise ValueError("retrieval scope requires retrieval_fixture")
        if "answer" in self.scope:
            if self.answer_contract is None:
                raise ValueError("answer scope requires answer_contract")
            if self.retrieval_fixture is None:
                raise ValueError("answer scope requires retrieval_fixture")
        if "e2e" in self.scope and self.expected_final_outcome is None:
            raise ValueError("e2e scope requires expected_final_outcome")
        if self.answer_contract is not None and self.retrieval_fixture is not None:
            chunk_ids = set(self.retrieval_fixture.relevant_chunk_ids)
            unknown_citations = (
                set(self.answer_contract.allowed_citation_ids) - chunk_ids
            )
            if unknown_citations:
                raise ValueError(
                    "allowed citations must be relevant retrieved chunks: "
                    + ", ".join(sorted(unknown_citations))
                )
        return self


class GoldDataset(StrictModel):
    dataset: str
    version: str
    status: Literal["human_review_required", "frozen"]
    primary_workflow: str
    primary_domain: PrimaryDomain
    notes: list[str]
    allowed_routes: list[Route]
    cases: list[GoldCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dataset_contract(self) -> GoldDataset:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case ids must be unique")
        if len(self.allowed_routes) != len(set(self.allowed_routes)):
            raise ValueError("allowed routes must be unique")
        allowed_routes = set(self.allowed_routes)
        for case in self.cases:
            if case.expected_route not in allowed_routes:
                raise ValueError(
                    f"case {case.case_id} uses route outside allowed_routes"
                )
        return self

    @classmethod
    def from_path(cls, path: Path) -> GoldDataset:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))


class RouteObservation(StrictModel):
    route: Route
    actions: list[str] = Field(default_factory=list)


class RetrievalObservation(StrictModel):
    retrieved_chunk_ids: list[str]

    @model_validator(mode="after")
    def validate_unique_ids(self) -> RetrievalObservation:
        if len(self.retrieved_chunk_ids) != len(set(self.retrieved_chunk_ids)):
            raise ValueError("observed retrieved chunk ids must be unique")
        return self


class AnswerObservation(StrictModel):
    covered_required_points: list[str] = Field(default_factory=list)
    detected_forbidden_claims: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    warned: bool
    unsupported_claim_count: int = Field(default=0, ge=0)
    summary_as_evidence_violation: bool = False

    @model_validator(mode="after")
    def validate_unique_labels(self) -> AnswerObservation:
        list_fields = {
            "covered_required_points": self.covered_required_points,
            "detected_forbidden_claims": self.detected_forbidden_claims,
            "citation_ids": self.citation_ids,
        }
        for field_name, values in list_fields.items():
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} values must be unique")
        return self


class CaseObservation(StrictModel):
    case_id: str
    scopes: list[DeterministicScope] = Field(min_length=1)
    state: dict[str, object] | None = None
    route: RouteObservation | None = None
    retrieval: RetrievalObservation | None = None
    answer: AnswerObservation | None = None

    @model_validator(mode="after")
    def validate_selected_scopes(self) -> CaseObservation:
        if len(self.scopes) != len(set(self.scopes)):
            raise ValueError("observation scopes must be unique")
        observed_by_scope = {
            "state": self.state,
            "route": self.route,
            "retrieval": self.retrieval,
            "answer": self.answer,
        }
        provided_scopes = {
            scope for scope, observed in observed_by_scope.items() if observed is not None
        }
        selected_scopes = set(self.scopes)
        if provided_scopes != selected_scopes:
            missing = sorted(selected_scopes - provided_scopes)
            unselected = sorted(provided_scopes - selected_scopes)
            details = []
            if missing:
                details.append("missing selected observations: " + ", ".join(missing))
            if unselected:
                details.append(
                    "observations provided outside selected scopes: "
                    + ", ".join(unselected)
                )
            raise ValueError("; ".join(details))
        if self.state is not None:
            _validate_state_values(self.state, "observed")
        return self


class ObservationDataset(StrictModel):
    dataset: str
    version: str
    profile: Literal["contract_probe", "runtime"]
    cases: list[CaseObservation] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> ObservationDataset:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("observation case ids must be unique")
        return self

    @classmethod
    def from_path(cls, path: Path) -> ObservationDataset:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))
