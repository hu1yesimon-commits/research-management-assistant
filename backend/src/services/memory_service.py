from __future__ import annotations

from dataclasses import dataclass

from services.memory_extractor import MemoryExtractor
from services.memory_store import MemoryStore


class MemoryServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass
class MemoryService:
    store: MemoryStore
    extractor: MemoryExtractor

    def refresh_candidates(self) -> list[dict]:
        logs = self.store.list_experiment_log_entries(limit=10_000)
        proposals = self.extractor.extract_semantic_proposals(logs)
        candidate_ids = [self.store.upsert_memory_candidate(proposal) for proposal in proposals]

        candidates = []
        for candidate_id in candidate_ids:
            candidate = self.store.get_memory_candidate(candidate_id)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def accept_candidate(self, candidate_id: int) -> dict:
        candidate = self.store.get_memory_candidate(candidate_id)
        if candidate is None:
            raise MemoryServiceError("memory candidate not found", status_code=404)
        if candidate["status"] != "pending":
            raise MemoryServiceError("only pending memory candidates can be accepted", status_code=400)
        if candidate["candidate_type"] != "semantic_proposal":
            raise MemoryServiceError("only semantic_proposal candidates can be accepted in MVP", status_code=400)

        semantic_id = self.store.upsert_semantic_memory_from_candidate(candidate)
        self.store.update_memory_candidate_status(candidate_id, "accepted")
        semantic = self.store.get_semantic_memory(semantic_id)
        if semantic is None:
            raise MemoryServiceError("confirmed semantic memory not found after accept", status_code=500)
        return semantic

    def reject_candidate(self, candidate_id: int) -> dict:
        candidate = self.store.get_memory_candidate(candidate_id)
        if candidate is None:
            raise MemoryServiceError("memory candidate not found", status_code=404)
        if candidate["status"] != "pending":
            raise MemoryServiceError("only pending memory candidates can be rejected", status_code=400)
        return self.store.update_memory_candidate_status(candidate_id, "rejected")

    def archive_semantic_memory(self, memory_id: int) -> dict:
        memory = self.store.get_semantic_memory(memory_id)
        if memory is None:
            raise MemoryServiceError("semantic memory not found", status_code=404)
        return self.store.archive_semantic_memory(memory_id)
