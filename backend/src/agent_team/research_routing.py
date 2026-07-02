import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ResearchRoutingSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["allow", "deny", "conflict", "none"]
    needs_clarify: bool = False
    confidence: float = Field(ge=0.0, le=1.0)


class ResearchRoutingParser:
    _TARGETS = {
        "paper",
        "papers",
        "literature",
        "study",
        "studies",
        "article",
        "articles",
        "evidence",
        "method",
        "methods",
    }
    _HOUSEHOLD_PAPER_PRODUCTS = {"towels", "plates", "bags", "cups"}
    _SINGLE_VERBS = {"find", "search", "discover", "recommend", "show", "need", "review"}
    _BOUNDARY_RE = re.compile(
        r"[.?!;]+|\b(?:but|however|yet)\b",
        flags=re.IGNORECASE,
    )
    _NEGATION_PREFIXES = (("do", "not"), ("never",), ("not",))

    def parse(self, message: str) -> ResearchRoutingSignal:
        normalized = self._normalize(message)
        outcomes = [
            outcome
            for clause in self._split_clauses(normalized)
            if (outcome := self._classify_clause(clause)) != "none"
        ]
        return self._aggregate(outcomes)

    def _normalize(self, message: str) -> str:
        normalized = unicodedata.normalize("NFKC", message)
        normalized = normalized.replace("’", "'").replace("‘", "'")
        normalized = re.sub(r"\bdon't\b", "do not", normalized, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", normalized).strip().lower()

    def _split_clauses(self, message: str) -> list[str]:
        clauses: list[str] = []
        for part in self._BOUNDARY_RE.split(message):
            pieces = re.split(r"\band\b", part, flags=re.IGNORECASE)
            current = pieces[0]
            for piece in pieces[1:]:
                if self._starts_retrieval_request(piece):
                    clauses.append(current)
                    current = piece
                else:
                    current = f"{current} and {piece}"
            clauses.append(current)
        return [clause.strip(" ,") for clause in clauses if clause.strip(" ,")]

    def _classify_clause(
        self, clause: str
    ) -> Literal["allow", "deny", "ambiguous", "none"]:
        tokens = re.findall(r"[a-z]+", clause)

        outcomes: set[str] = set()
        for start, verb_end in self._request_spans(tokens):
            target_index = self._target_index(tokens, verb_end)
            if target_index is None:
                continue
            between = tokens[verb_end:target_index]
            is_negated = self._has_negation_prefix(tokens, start) or "no" in between
            outcomes.add("deny" if is_negated else "allow")

        if outcomes == {"allow"}:
            return "allow"
        if outcomes == {"deny"}:
            return "deny"
        if outcomes == {"allow", "deny"}:
            return "ambiguous"
        if self._has_ambiguous_request(tokens):
            return "ambiguous"
        return "none"

    def _request_spans(self, tokens: list[str]):
        for index, token in enumerate(tokens):
            if token in self._SINGLE_VERBS:
                yield index, index + 1
            elif token == "look" and tokens[index : index + 2] == ["look", "for"]:
                yield index, index + 2

    def _target_index(self, tokens: list[str], verb_end: int) -> int | None:
        upper_bound = min(len(tokens), verb_end + 8)
        for index in range(verb_end, upper_bound):
            if tokens[index] in self._TARGETS:
                if (
                    tokens[index] == "paper"
                    and index + 1 < len(tokens)
                    and tokens[index + 1] in self._HOUSEHOLD_PAPER_PRODUCTS
                ):
                    continue
                return index
        return None

    def _starts_retrieval_request(self, clause: str) -> bool:
        tokens = re.findall(r"[a-z]+", clause)
        start = 0
        if tokens[:1] == ["i"]:
            start = 1
        for prefix in self._NEGATION_PREFIXES:
            if tuple(tokens[start : start + len(prefix)]) == prefix:
                start += len(prefix)
                break
        return any(request_start == start for request_start, _ in self._request_spans(tokens))

    def _has_negation_prefix(self, tokens: list[str], request_start: int) -> bool:
        prefix_tokens = tokens[:request_start]
        return any(
            tuple(prefix_tokens[-len(prefix) :]) == prefix
            for prefix in self._NEGATION_PREFIXES
        )

    def _has_ambiguous_request(self, tokens: list[str]) -> bool:
        for index, token in enumerate(tokens):
            if token not in {"help", "want"}:
                continue
            if self._target_index(tokens, index + 1) is not None:
                return True
        return False

    def _aggregate(self, outcomes: list[str]) -> ResearchRoutingSignal:
        distinct = set(outcomes)
        if "ambiguous" in distinct or {"allow", "deny"} <= distinct:
            confidence = 0.5 if "ambiguous" in distinct else 1.0
            return ResearchRoutingSignal(
                decision="conflict",
                needs_clarify=True,
                confidence=confidence,
            )
        if distinct == {"allow"}:
            return ResearchRoutingSignal(decision="allow", confidence=1.0)
        if distinct == {"deny"}:
            return ResearchRoutingSignal(decision="deny", confidence=1.0)
        return ResearchRoutingSignal(decision="none", confidence=1.0)
