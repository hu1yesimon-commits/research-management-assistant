import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ResearchRoutingSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["allow", "deny", "conflict", "review_existing", "none"]
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
    _HOUSEHOLD_PAPER_PRODUCTS = {
        "towel",
        "towels",
        "plate",
        "plates",
        "bag",
        "bags",
        "cup",
        "cups",
    }
    _SINGLE_VERBS = {"find", "search", "discover", "recommend", "show", "need"}
    _FRESH_REVIEW_MODIFIERS = {"new", "recent", "latest"}
    _FRESH_TARGET_MODIFIERS = {
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "single",
        "some",
        "top",
        "best",
        "relevant",
        "highly",
        "very",
        "most",
    }
    _FRESH_REVIEW_TARGETS = {
        "paper",
        "papers",
        "literature",
        "study",
        "studies",
        "article",
        "articles",
    }
    _EXISTING_REVIEW_MODIFIERS = {"existing", "saved", "my", "current", "our"}
    _EXISTING_REVIEW_TARGETS = {
        "paper",
        "papers",
        "literature",
        "memory",
        "memories",
        "material",
        "materials",
        "notes",
    }
    _BARE_REVIEW_MODIFIERS = _FRESH_TARGET_MODIFIERS | _FRESH_REVIEW_MODIFIERS | {
        "a",
        "an",
        "the",
        "peer",
        "reviewed",
    }
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
    ) -> Literal[
        "allow",
        "deny",
        "ambiguous",
        "review_ambiguous",
        "review_existing",
        "none",
    ]:
        tokens = re.findall(r"[a-z]+|\d+", clause)

        outcomes: set[str] = set()
        standalone_outcome = self._classify_standalone_fresh(tokens)
        if standalone_outcome != "none":
            outcomes.add(standalone_outcome)
        for start, verb_end in self._request_spans(tokens):
            target_index = self._target_index(tokens, verb_end)
            if target_index is None:
                continue
            between = tokens[verb_end:target_index]
            is_negated = self._has_negation_prefix(tokens, start) or "no" in between
            outcomes.add("deny" if is_negated else "allow")

        review_outcome = self._classify_review(tokens, has_fresh_allow="allow" in outcomes)
        if review_outcome != "none":
            outcomes.add(review_outcome)
        if self._has_ambiguous_request(tokens):
            outcomes.add("ambiguous")
        return self._combine_clause_outcomes(outcomes)

    def _request_spans(self, tokens: list[str]):
        for index, token in enumerate(tokens):
            if token in self._SINGLE_VERBS:
                yield index, index + 1
            elif token == "look" and tokens[index : index + 2] == ["look", "for"]:
                yield index, index + 2

    def _target_index(
        self,
        tokens: list[str],
        search_start: int,
    ) -> int | None:
        upper_bound = min(len(tokens), search_start + 8)
        for index in range(search_start, upper_bound):
            if self._is_valid_academic_target(tokens, index):
                return index
        return None

    def _is_valid_academic_target(self, tokens: list[str], index: int) -> bool:
        if tokens[index] not in self._TARGETS:
            return False
        return not (
            tokens[index] == "paper"
            and index + 1 < len(tokens)
            and tokens[index + 1] in self._HOUSEHOLD_PAPER_PRODUCTS
        )

    def _classify_review(
        self, tokens: list[str], *, has_fresh_allow: bool
    ) -> Literal[
        "allow", "deny", "review_ambiguous", "review_existing", "none"
    ]:
        for review_index, token in enumerate(tokens):
            if token != "review":
                continue
            object_start = review_index + 1
            if self._matches_direct_existing_review(tokens, object_start):
                outcome = "review_existing"
            elif self._matches_direct_fresh_review(tokens, object_start):
                outcome = "allow"
            elif self._matches_direct_bare_review(tokens, object_start):
                outcome = "review_ambiguous"
            else:
                continue
            if self._has_negation_prefix(tokens, review_index):
                return "deny"
            if has_fresh_allow:
                return "allow"
            return outcome
        return "none"

    def _matches_direct_existing_review(
        self, tokens: list[str], object_start: int
    ) -> bool:
        index = object_start
        if tokens[index : index + 1] == ["the"]:
            index += 1

        if self._matches_existing_material_phrase(tokens, index):
            return True

        modifier_count = 0
        while (
            index < len(tokens)
            and tokens[index] in self._EXISTING_REVIEW_MODIFIERS
        ):
            modifier_count += 1
            index += 1
        if modifier_count == 0 or index >= len(tokens):
            return False
        if self._matches_existing_material_phrase(tokens, index):
            return True
        if tokens[index] not in self._EXISTING_REVIEW_TARGETS:
            return False
        return tokens[index] != "paper" or self._is_valid_academic_target(tokens, index)

    def _matches_existing_material_phrase(
        self, tokens: list[str], start: int
    ) -> bool:
        return tokens[start : start + 1] == ["notes"] or tokens[
            start : start + 2
        ] in (["experiment", "logs"], ["research", "notes"])

    def _matches_direct_fresh_review(
        self, tokens: list[str], object_start: int
    ) -> bool:
        marker_index = object_start
        if tokens[marker_index : marker_index + 1] == ["the"]:
            marker_index += 1
        return self._fresh_target_index(tokens, marker_index) is not None

    def _matches_direct_bare_review(
        self, tokens: list[str], object_start: int
    ) -> bool:
        upper_bound = min(len(tokens), object_start + 8)
        for index in range(object_start, upper_bound):
            if self._is_valid_academic_target(tokens, index):
                return True
            if tokens[index].isdigit() or tokens[index] in self._BARE_REVIEW_MODIFIERS:
                continue
            return False
        return False

    def _classify_standalone_fresh(
        self, tokens: list[str]
    ) -> Literal["allow", "deny", "none"]:
        marker_index = 0
        is_negated = False
        if tokens[:2] == ["do", "not"]:
            marker_index = 2
            is_negated = True
        elif tokens[:1] and tokens[0] in {"no", "not", "never"}:
            marker_index = 1
            is_negated = True
        if marker_index >= len(tokens):
            return "none"
        if tokens[marker_index] not in self._FRESH_REVIEW_MODIFIERS:
            return "none"
        if self._fresh_target_index(tokens, marker_index) is None:
            return "none"
        return "deny" if is_negated else "allow"

    def _fresh_target_index(self, tokens: list[str], marker_index: int) -> int | None:
        if tokens[marker_index : marker_index + 1] not in (
            ["new"],
            ["recent"],
            ["latest"],
        ):
            return None
        index = marker_index + 1
        modifier_count = 0
        while index < len(tokens) and modifier_count < 2:
            if tokens[index].isdigit() or tokens[index] in self._FRESH_TARGET_MODIFIERS:
                modifier_count += 1
                index += 1
                continue
            break
        if index >= len(tokens) or tokens[index] not in self._FRESH_REVIEW_TARGETS:
            return None
        return index if self._is_valid_academic_target(tokens, index) else None

    def _combine_clause_outcomes(self, outcomes: set[str]):
        if "ambiguous" in outcomes or {"allow", "deny"} <= outcomes:
            return "ambiguous"
        if "allow" in outcomes:
            return "allow"
        if "review_ambiguous" in outcomes:
            return "review_ambiguous"
        if "review_existing" in outcomes:
            return "review_existing"
        if "deny" in outcomes:
            return "deny"
        return "none"

    def _starts_retrieval_request(self, clause: str) -> bool:
        tokens = re.findall(r"[a-z]+|\d+", clause)
        if self._classify_standalone_fresh(tokens) != "none":
            return True
        start = 0
        if tokens[:1] == ["i"]:
            start = 1
        for prefix in self._NEGATION_PREFIXES:
            if tuple(tokens[start : start + len(prefix)]) == prefix:
                start += len(prefix)
                break
        return tokens[start : start + 1] == ["review"] or any(
            request_start == start for request_start, _ in self._request_spans(tokens)
        )

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
        if "allow" in distinct:
            return ResearchRoutingSignal(decision="allow", confidence=1.0)
        if "review_ambiguous" in distinct:
            return ResearchRoutingSignal(
                decision="conflict",
                needs_clarify=True,
                confidence=0.5,
            )
        if "review_existing" in distinct:
            return ResearchRoutingSignal(decision="review_existing", confidence=1.0)
        if distinct == {"deny"}:
            return ResearchRoutingSignal(decision="deny", confidence=1.0)
        return ResearchRoutingSignal(decision="none", confidence=1.0)
