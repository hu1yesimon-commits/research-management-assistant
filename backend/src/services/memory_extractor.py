from __future__ import annotations

import re
from collections import defaultdict


ALIASES = {
    "focal loss": "focal loss",
    "prauc": "prauc",
    "pr auc": "prauc",
}


def normalize_memory_object(value: str) -> str:
    normalized = value.strip().lower().replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return ALIASES.get(normalized, normalized)


class MemoryExtractor:
    threshold = 3

    def extract_semantic_proposals(self, logs: list[dict]) -> list[dict]:
        facts: dict[tuple[str, str, str, str], list[int]] = defaultdict(list)

        for log in logs:
            log_id = int(log["id"])
            subject = normalize_memory_object(log["task"])

            self._add_fact(facts, "research_topic", subject, "focuses_on", log["task"], log_id)
            self._add_fact(facts, "experiment_target", subject, "uses_object", log["model"], log_id)
            self._add_fact(facts, "experiment_target", subject, "uses_object", log["dataset"], log_id)

            for method in log.get("tried_methods", []):
                self._add_fact(facts, "experiment_target", subject, "uses_object", method, log_id)

            for tag in log.get("tags", []):
                normalized_tag = normalize_memory_object(tag)
                if normalized_tag in {"lightweight", "可解释", "interpretability", "offline", "deterministic"}:
                    self._add_fact(facts, "user_preference", "user", "prefers", normalized_tag, log_id)

            trend = self._build_result_trend(log)
            if trend:
                self._add_fact(facts, "result_trend", subject, "shows_trend", trend, log_id)

            block = self._build_recurring_block(log)
            if block:
                self._add_fact(facts, "recurring_block", subject, "blocked_by", block, log_id)

        return self._to_candidates(facts)

    def _add_fact(
        self,
        facts: dict[tuple[str, str, str, str], list[int]],
        category: str,
        subject: str,
        predicate: str,
        object_value: str,
        log_id: int,
    ) -> None:
        normalized_object = normalize_memory_object(object_value)
        if normalized_object:
            facts[(category, subject, predicate, normalized_object)].append(log_id)

    def _build_result_trend(self, log: dict) -> str | None:
        methods = log.get("tried_methods", [])
        observation = normalize_memory_object(log.get("observation", ""))
        if not methods or not observation:
            return None
        return f"{normalize_memory_object(methods[-1])} -> {observation}"

    def _build_recurring_block(self, log: dict) -> str | None:
        text = " ".join(
            [
                log.get("metric_problem", ""),
                log.get("observation", ""),
                log.get("goal", ""),
            ]
        )
        lowered = normalize_memory_object(text)
        if "heavy" in lowered or "不稳定" in lowered or "low" in lowered:
            return lowered
        return None

    def _to_candidates(self, facts: dict[tuple[str, str, str, str], list[int]]) -> list[dict]:
        candidates = []
        for (category, subject, predicate, object_value), log_ids in sorted(facts.items()):
            unique_log_ids = sorted(set(log_ids))
            if len(unique_log_ids) < self.threshold:
                continue
            candidates.append(
                {
                    "candidate_type": "semantic_proposal",
                    "category": category,
                    "subject": subject,
                    "predicate": predicate,
                    "object": object_value,
                    "summary": f"{subject} {predicate} {object_value}",
                    "source_log_ids": unique_log_ids,
                    "evidence_count": len(unique_log_ids),
                    "score": min(1.0, len(unique_log_ids) / 5),
                    "status": "pending",
                }
            )
        return candidates
