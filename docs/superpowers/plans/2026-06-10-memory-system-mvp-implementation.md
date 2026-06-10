# Memory System MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a default-offline, user-confirmed long-term memory layer for Research Management Assistant using existing SQLite storage and structured experiment logs.

**Architecture:** Keep `experiment_log_entries` as the episodic evidence layer, add `memory_candidates` as the auto-suggested review buffer, and add `semantic_memory` as the confirmed long-term fact layer. Query rewrite and Idea Assistant should consume only confirmed semantic memory plus a small recent episodic window, while Chroma/vector retrieval remains dedicated to paper knowledge chunks.

**Tech Stack:** FastAPI, Pydantic, SQLite `MemoryStore`, deterministic Python extraction rules, existing LangGraph discovery flow, pytest.

---

## Source Spec

Implement from:

- `docs/superpowers/specs/2026-06-10-memory-system-mvp-design.md`

This plan must not expand scope into:

- saving all chat transcript as memory
- persisting discovery candidates as long-term memory
- treating knowledge chunks as user memory
- Neo4j, Qdrant, or a new primary persistence backend
- automatic mutation of confirmed semantic memory
- general chat-agent memory
- default real DeepSeek/OpenAI/BGE-M3/Chroma calls
- frontend redesign

## Current Baseline

Already implemented before this plan:

- `experiment_log_entries` table in `backend/src/services/memory_store.py`
- `add_experiment_log_entry()` and `list_experiment_log_entries()`
- `POST /experiments/logs`
- `GET /experiments/logs`
- `POST /ideas/recommend`
- `MemoryStore.build_memory_context()`, currently based on legacy `/logs`

Important implication:

- Do not reimplement structured experiment logs. Phase 1 should lock the contract and switch the query-rewrite context source.

## File Map

Backend files to modify:

- `backend/src/services/schemas.py`
  - Add memory enum types and request/response schemas.
  - Keep existing experiment-log and idea schemas stable.

- `backend/src/services/memory_store.py`
  - Add `memory_candidates` and `semantic_memory` tables.
  - Add candidate CRUD/review methods.
  - Add semantic memory CRUD/review methods.
  - Replace `build_memory_context()` internals with confirmed semantic memory plus recent 3 structured logs.

- `backend/src/services/memory_extractor.py`
  - New file.
  - Define deterministic object normalization and candidate extraction.
  - Keep extraction LLM-free.

- `backend/src/services/memory_service.py`
  - New file.
  - Orchestrate extraction, candidate upsert/list/reject/accept, semantic confirmation, and minimal stale/conflict review contract.

- `backend/src/services/idea_service.py`
  - Add optional memory context input to the deterministic generator path only after semantic memory is available.
  - Preserve no-source fallback behavior.

- `backend/src/main.py`
  - Add narrow `/memory/*` endpoints.
  - Wire service dependencies.
  - Keep `/memory/summary` backward compatible or extend it conservatively.

- `backend/src/graph/nodes.py`
  - No direct memory logic beyond continuing to call `memory_store.build_memory_context()`.
  - Update tests to prove the assembled context changed.

Backend tests to modify/create:

- `backend/src/tests/test_memory_store.py`
- `backend/src/tests/test_memory_extractor.py`
- `backend/src/tests/test_memory_service.py`
- `backend/src/tests/test_query_rewriter.py`
- `backend/src/tests/test_paper_discovery_graph.py`
- `backend/src/tests/test_idea_service.py`
- `backend/src/tests/test_api_mvp.py`

Docs to modify after implementation:

- `README.md`
  - Document only completed endpoints and deterministic/offline behavior.
  - Do not claim stale/conflict automation is intelligent; describe it as review-gated.

## API Contract Draft

Use these endpoint shapes unless user review changes them.

- `GET /memory/candidates`
  - Query params: `status=pending`, optional `candidate_type`, optional `category`.
  - Returns `list[MemoryCandidate]`.

- `POST /memory/candidates/refresh`
  - Recomputes deterministic proposals from all structured logs.
  - Creates or updates `pending` semantic proposals only.
  - Does not create confirmed semantic memory.

- `POST /memory/candidates/{candidate_id}/accept`
  - Marks candidate `accepted`.
  - Creates or updates one `semantic_memory` row with `status="confirmed"`.
  - Returns `SemanticMemoryEntry`.

- `POST /memory/candidates/{candidate_id}/reject`
  - Marks candidate `rejected`.
  - Does not create semantic memory.
  - Returns `MemoryCandidate`.

- `GET /memory/semantic`
  - Query params: `status=confirmed`, optional `category`, optional `predicate`.
  - Returns `list[SemanticMemoryEntry]`.

- `POST /memory/semantic/{memory_id}/archive`
  - Marks semantic memory `archived`.
  - This is an explicit user action in MVP.
  - Returns `SemanticMemoryEntry`.

## Review Gates

Subagents can execute:

- SQLite schema additions
- Pydantic schema additions
- deterministic normalization and extraction
- candidate refresh/list/reject/accept plumbing
- semantic memory list/archive plumbing
- query-rewrite context assembly
- API tests and service tests
- README updates after implementation

The user should personally review:

- final `category` enum boundaries
- final `predicate` enum boundaries
- `result_trend` object template
- whether candidate threshold remains exactly 3 global occurrences
- whether stale/conflict remain manual-review-only for MVP
- endpoint names before frontend work depends on them
- README wording about what is implemented versus planned

## Phase 1: Episodic Contract And Query-Rewrite Context

**Goal:** Keep structured logs as the episodic evidence layer and switch query rewrite from legacy simple logs to `confirmed semantic memory + recent 3 experiment_log_entries`.

**Files:**

- Modify: `backend/src/services/memory_store.py`
- Modify: `backend/src/tests/test_memory_store.py`
- Modify: `backend/src/tests/test_paper_discovery_graph.py`
- Modify: `backend/src/services/query_rewriter.py`

### Task 1.1: Lock Recent Structured Log Context

- [ ] **Step 1: Add failing store test for recent structured logs**

Add a test to `backend/src/tests/test_memory_store.py`:

```python
def test_build_memory_context_uses_recent_three_structured_logs_not_legacy_logs(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    store.add_experiment_log("legacy note should not enter rewrite", tags=["legacy"])

    for index in range(4):
        store.add_experiment_log_entry(
            {
                "task": f"task-{index}",
                "model": f"model-{index}",
                "dataset": f"dataset-{index}",
                "metric_problem": f"metric problem {index}",
                "tried_methods": [f"method-{index}"],
                "observation": f"observation {index}",
                "goal": f"goal {index}",
                "tags": [f"tag-{index}"],
            }
        )

    context = store.build_memory_context()

    assert "legacy note should not enter rewrite" not in context
    assert "Recent episodic memory" in context
    assert "task-3" in context
    assert "task-2" in context
    assert "task-1" in context
    assert "task-0" not in context
```

- [ ] **Step 2: Run failing store test**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_store.py::test_build_memory_context_uses_recent_three_structured_logs_not_legacy_logs -q
```

Expected before implementation:

- Fails because `build_memory_context()` still reads legacy `experiment_logs`.

- [ ] **Step 3: Implement recent structured-log context**

Modify `MemoryStore.build_memory_context()` so it:

- reads `list_semantic_memory(status="confirmed")` if that method exists after Phase 3, otherwise starts with an empty semantic section
- reads `list_experiment_log_entries(limit=3)`
- formats a small, stable text context
- never reads legacy `experiment_logs`

Target output shape:

```text
Confirmed semantic memory:
- [category/predicate] subject -> object: summary

Recent episodic memory:
- task=<task>; model=<model>; dataset=<dataset>; metric_problem=<metric_problem>; tried_methods=<comma-separated methods>; observation=<observation>; goal=<goal>; tags=<comma-separated tags>
```

- [ ] **Step 4: Run focused store tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_store.py -q
```

Expected:

- Existing structured-log tests pass.
- The old legacy context test should be updated or replaced, not kept with obsolete assertions.

### Task 1.2: Prove Advanced Query Rewrite Uses The New Context

- [ ] **Step 1: Update graph test**

Update `test_advanced_graph_uses_memory_context_for_rewritten_queries` in `backend/src/tests/test_paper_discovery_graph.py`:

```python
def test_advanced_graph_uses_structured_memory_context_for_rewritten_queries(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    store.add_experiment_log("legacy heavy note should be ignored", tags=["block"])
    store.add_experiment_log_entry(
        {
            "task": "graph reconstruction",
            "model": "lightweight GNN",
            "dataset": "citation graph",
            "metric_problem": "interpretability is weak",
            "tried_methods": ["modular loss"],
            "observation": "model is too heavy and hard to interpret",
            "goal": "improve interpretability without adding heavy modules",
            "tags": ["lightweight", "interpretability"],
        }
    )

    graph = build_paper_discovery_graph(
        search_service=FakeSearchService(),
        judge=FakeJudge(),
        memory_store=store,
        query_rewriter=QueryRewriter(),
    )

    result = graph.invoke(
        {
            "mode": "advanced",
            "user_query": "graph reconstruction",
            "memory_context": "",
            "rewritten_queries": [],
            "raw_results": [],
            "normalized_papers": [],
            "deduped_papers": [],
            "judge_results": [],
            "ranked_candidates": [],
        }
    )

    assert "Recent episodic memory" in result["memory_context"]
    assert "legacy heavy note should be ignored" not in result["memory_context"]
    assert "graph reconstruction lightweight" in result["rewritten_queries"]
    assert "graph reconstruction interpretability" in result["rewritten_queries"]
```

- [ ] **Step 2: Run graph test**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_paper_discovery_graph.py::test_advanced_graph_uses_structured_memory_context_for_rewritten_queries -q
```

Expected:

- Passes after `build_memory_context()` is switched.

## Phase 2: Memory Candidates And Deterministic Extraction

**Goal:** Add `memory_candidates`, object normalization, and deterministic `semantic_proposal` generation after 3 global occurrences.

**Files:**

- Modify: `backend/src/services/schemas.py`
- Modify: `backend/src/services/memory_store.py`
- Create: `backend/src/services/memory_extractor.py`
- Create: `backend/src/services/memory_service.py`
- Modify: `backend/src/tests/test_memory_store.py`
- Create: `backend/src/tests/test_memory_extractor.py`
- Create: `backend/src/tests/test_memory_service.py`

### Task 2.1: Add Candidate Schemas And Table

- [ ] **Step 1: Add schema enums**

Add to `backend/src/services/schemas.py`:

```python
class MemoryCategory(str, Enum):
    research_topic = "research_topic"
    experiment_target = "experiment_target"
    result_trend = "result_trend"
    recurring_block = "recurring_block"
    user_preference = "user_preference"


class MemoryPredicate(str, Enum):
    focuses_on = "focuses_on"
    uses_object = "uses_object"
    shows_trend = "shows_trend"
    blocked_by = "blocked_by"
    prefers = "prefers"
    avoids = "avoids"


class MemoryCandidateType(str, Enum):
    semantic_proposal = "semantic_proposal"
    stale_proposal = "stale_proposal"
    conflict_proposal = "conflict_proposal"


class MemoryCandidateStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    expired = "expired"
```

- [ ] **Step 2: Add candidate response schema**

Add to `backend/src/services/schemas.py`:

```python
class MemoryCandidate(BaseModel):
    id: int
    candidate_type: MemoryCandidateType
    category: MemoryCategory
    subject: str
    predicate: MemoryPredicate
    object: str
    summary: str
    source_log_ids: list[int] = Field(default_factory=list)
    evidence_count: int
    score: float = Field(ge=0, le=1)
    status: MemoryCandidateStatus
    created_at: str
    reviewed_at: str | None = None
```

- [ ] **Step 3: Add failing table test**

Add to `backend/src/tests/test_memory_store.py`:

```python
def test_initialize_creates_memory_candidates_table(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    store = MemoryStore(str(db_path))

    store.initialize()

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    connection.close()

    assert "memory_candidates" in {row[0] for row in rows}
```

- [ ] **Step 4: Run failing test**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_store.py::test_initialize_creates_memory_candidates_table -q
```

Expected before implementation:

- Fails because `memory_candidates` does not exist.

- [ ] **Step 5: Add `memory_candidates` table**

Add table creation to `MemoryStore.initialize()` exactly matching the spec columns.

- [ ] **Step 6: Add store methods**

Add these public methods to `MemoryStore` with the exact behavior described below:

```python
def upsert_memory_candidate(self, candidate: dict) -> int:
    """Insert a new candidate or update the existing candidate with the same stable key."""

def list_memory_candidates(
    self,
    status: str = "pending",
    candidate_type: str | None = None,
    category: str | None = None,
) -> list[dict]:
    """Return candidates filtered by status, candidate_type, and category."""

def get_memory_candidate(self, candidate_id: int) -> dict | None:
    """Return one candidate by id, or None if it does not exist."""

def update_memory_candidate_status(self, candidate_id: int, status: str) -> dict:
    """Set status and reviewed_at, then return the updated candidate."""
```

Rules:

- Upsert uniqueness is `candidate_type + category + subject + predicate + object`.
- If a duplicate pending candidate exists, update `source_log_ids_json`, `evidence_count`, `score`, and keep original `created_at`.
- `update_memory_candidate_status()` sets `reviewed_at` for `accepted`, `rejected`, and `expired`.

- [ ] **Step 7: Add store behavior tests**

Add tests proving:

- candidate can be inserted and listed
- duplicate candidate is updated instead of duplicated
- rejected candidate disappears from default pending list
- `source_log_ids_json` round-trips as `source_log_ids`

- [ ] **Step 8: Run focused store tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_store.py -q
```

Expected:

- All store tests pass.

### Task 2.2: Add Deterministic Extractor

- [ ] **Step 1: Add failing extractor tests**

Create `backend/src/tests/test_memory_extractor.py`:

```python
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
```

- [ ] **Step 2: Run failing extractor tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_extractor.py -q
```

Expected before implementation:

- Fails because `memory_extractor.py` does not exist.

- [ ] **Step 3: Implement `memory_extractor.py`**

Create `backend/src/services/memory_extractor.py` with:

```python
from __future__ import annotations

import re
from collections import defaultdict


ALIASES = {
    "focal-loss": "focal loss",
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
                if tag in {"lightweight", "可解释", "interpretability", "offline", "deterministic"}:
                    self._add_fact(facts, "user_preference", "user", "prefers", tag, log_id)

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
        if "heavy" in lowered or "too heavy" in lowered or "不稳定" in lowered or "low" in lowered:
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
```

- [ ] **Step 4: Run extractor tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_extractor.py -q
```

Expected:

- All extractor tests pass.

### Task 2.3: Add Candidate Refresh Service

- [ ] **Step 1: Add failing service test**

Create `backend/src/tests/test_memory_service.py`:

```python
from services.memory_extractor import MemoryExtractor
from services.memory_service import MemoryService
from services.memory_store import MemoryStore


def add_repeated_logs(store: MemoryStore):
    for _ in range(3):
        store.add_experiment_log_entry(
            {
                "task": "defect classification",
                "model": "1D-CNN",
                "dataset": "bearing fault dataset",
                "metric_problem": "minority PRAUC is low",
                "tried_methods": ["focal loss"],
                "observation": "recall improves but precision collapses",
                "goal": "improve PRAUC without making model too heavy",
                "tags": ["lightweight"],
            }
        )


def test_refresh_candidates_creates_pending_semantic_proposals(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    add_repeated_logs(store)
    service = MemoryService(store=store, extractor=MemoryExtractor())

    candidates = service.refresh_candidates()

    assert candidates
    assert all(candidate["status"] == "pending" for candidate in candidates)
    assert any(candidate["object"] == "focal loss" for candidate in candidates)
    assert store.list_memory_candidates()
```

- [ ] **Step 2: Run failing service test**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_service.py::test_refresh_candidates_creates_pending_semantic_proposals -q
```

Expected before implementation:

- Fails because `memory_service.py` does not exist or store candidate methods do not exist.

- [ ] **Step 3: Implement `MemoryService.refresh_candidates()`**

Create `backend/src/services/memory_service.py`:

```python
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
        return [
            self.store.get_memory_candidate(candidate_id)
            for candidate_id in candidate_ids
            if self.store.get_memory_candidate(candidate_id) is not None
        ]
```

- [ ] **Step 4: Run service tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_service.py -q
```

Expected:

- Candidate refresh tests pass.

## Phase 3: Semantic Memory Confirmation

**Goal:** Add `semantic_memory`, accept/reject candidate flows, and expose only confirmed semantic memory to long-term contexts.

**Files:**

- Modify: `backend/src/services/schemas.py`
- Modify: `backend/src/services/memory_store.py`
- Modify: `backend/src/services/memory_service.py`
- Modify: `backend/src/tests/test_memory_store.py`
- Modify: `backend/src/tests/test_memory_service.py`

### Task 3.1: Add Semantic Memory Schemas And Table

- [ ] **Step 1: Add schema enum and response**

Add to `backend/src/services/schemas.py`:

```python
class SemanticMemoryStatus(str, Enum):
    confirmed = "confirmed"
    archived = "archived"


class SemanticMemoryEntry(BaseModel):
    id: int
    category: MemoryCategory
    subject: str
    predicate: MemoryPredicate
    object: str
    summary: str
    confidence: float = Field(ge=0, le=1)
    support_count: int
    supporting_log_ids: list[int] = Field(default_factory=list)
    status: SemanticMemoryStatus
    last_confirmed_at: str
    created_at: str
    updated_at: str
```

- [ ] **Step 2: Add failing table test**

Add to `backend/src/tests/test_memory_store.py`:

```python
def test_initialize_creates_semantic_memory_table(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    store = MemoryStore(str(db_path))

    store.initialize()

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    connection.close()

    assert "semantic_memory" in {row[0] for row in rows}
```

- [ ] **Step 3: Run failing test**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_store.py::test_initialize_creates_semantic_memory_table -q
```

Expected before implementation:

- Fails because `semantic_memory` does not exist.

- [ ] **Step 4: Add table and store methods**

Add `semantic_memory` table exactly matching the spec.

Add these public methods to `MemoryStore` with the exact behavior described below:

```python
def upsert_semantic_memory_from_candidate(self, candidate: dict) -> int:
    """Create or refresh a confirmed semantic memory row from an accepted candidate."""

def list_semantic_memory(
    self,
    status: str = "confirmed",
    category: str | None = None,
    predicate: str | None = None,
) -> list[dict]:
    """Return semantic memory filtered by status, category, and predicate."""

def get_semantic_memory(self, memory_id: int) -> dict | None:
    """Return one semantic memory row by id, or None if it does not exist."""

def archive_semantic_memory(self, memory_id: int) -> dict:
    """Set semantic memory status to archived and return the updated row."""
```

Rules:

- Upsert uniqueness is `category + subject + predicate + object`.
- Confirmation sets `status="confirmed"` and updates `last_confirmed_at`.
- Archiving is explicit and never automatic.

- [ ] **Step 5: Add store behavior tests**

Add tests proving:

- confirmed semantic memory can be inserted from a candidate
- `list_semantic_memory()` returns only confirmed by default
- archived semantic memory disappears from default list
- support ids round-trip as `supporting_log_ids`

### Task 3.2: Add Accept/Reject Candidate Flow

- [ ] **Step 1: Add failing service tests**

Add to `backend/src/tests/test_memory_service.py`:

```python
def test_accept_candidate_creates_confirmed_semantic_memory(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    candidate_id = store.upsert_memory_candidate(
        {
            "candidate_type": "semantic_proposal",
            "category": "experiment_target",
            "subject": "defect classification",
            "predicate": "uses_object",
            "object": "focal loss",
            "summary": "defect classification repeatedly uses focal loss",
            "source_log_ids": [1, 2, 3],
            "evidence_count": 3,
            "score": 0.8,
            "status": "pending",
        }
    )
    service = MemoryService(store=store, extractor=MemoryExtractor())

    semantic = service.accept_candidate(candidate_id)

    assert semantic["status"] == "confirmed"
    assert semantic["object"] == "focal loss"
    assert store.get_memory_candidate(candidate_id)["status"] == "accepted"


def test_reject_candidate_does_not_create_semantic_memory(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    candidate_id = store.upsert_memory_candidate(
        {
            "candidate_type": "semantic_proposal",
            "category": "experiment_target",
            "subject": "defect classification",
            "predicate": "uses_object",
            "object": "focal loss",
            "summary": "defect classification repeatedly uses focal loss",
            "source_log_ids": [1, 2, 3],
            "evidence_count": 3,
            "score": 0.8,
            "status": "pending",
        }
    )
    service = MemoryService(store=store, extractor=MemoryExtractor())

    rejected = service.reject_candidate(candidate_id)

    assert rejected["status"] == "rejected"
    assert store.list_semantic_memory() == []
```

- [ ] **Step 2: Run failing service tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_service.py -q
```

Expected before implementation:

- Fails until `accept_candidate()` and `reject_candidate()` exist.

- [ ] **Step 3: Implement service methods**

Add to `MemoryService`:

```python
def accept_candidate(self, candidate_id: int) -> dict:
    candidate = self.store.get_memory_candidate(candidate_id)
    if candidate is None:
        raise MemoryServiceError("memory candidate not found", status_code=404)
    if candidate["status"] != "pending":
        raise MemoryServiceError("only pending memory candidates can be accepted", status_code=400)
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
```

- [ ] **Step 4: Run service and store tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_store.py backend/src/tests/test_memory_service.py -q
```

Expected:

- Store and service memory tests pass.

### Task 3.3: Include Confirmed Semantic Memory In Rewrite Context

- [ ] **Step 1: Add store test**

Add to `backend/src/tests/test_memory_store.py`:

```python
def test_build_memory_context_includes_confirmed_semantic_before_recent_logs(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    candidate_id = store.upsert_memory_candidate(
        {
            "candidate_type": "semantic_proposal",
            "category": "user_preference",
            "subject": "user",
            "predicate": "prefers",
            "object": "lightweight",
            "summary": "User repeatedly prefers lightweight approaches.",
            "source_log_ids": [1, 2, 3],
            "evidence_count": 3,
            "score": 0.8,
            "status": "pending",
        }
    )
    candidate = store.get_memory_candidate(candidate_id)
    store.upsert_semantic_memory_from_candidate(candidate)
    store.add_experiment_log_entry(
        {
            "task": "graph reconstruction",
            "model": "GNN",
            "dataset": "citation graph",
            "metric_problem": "interpretability is weak",
            "tried_methods": ["modular loss"],
            "observation": "loss improves stability",
            "goal": "keep the model interpretable",
            "tags": ["interpretability"],
        }
    )

    context = store.build_memory_context()

    semantic_index = context.index("Confirmed semantic memory")
    episodic_index = context.index("Recent episodic memory")
    assert semantic_index < episodic_index
    assert "user prefers lightweight" in context
    assert "graph reconstruction" in context
```

- [ ] **Step 2: Run store test**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_store.py::test_build_memory_context_includes_confirmed_semantic_before_recent_logs -q
```

Expected:

- Passes after semantic memory methods and context assembly are implemented.

## Phase 4: API, Idea Assistant Context, And Review-Gated Stale/Conflict

**Goal:** Expose memory review APIs, connect confirmed memory to Idea Assistant context, and keep stale/conflict as explicit review contracts rather than automatic fact mutation.

**Files:**

- Modify: `backend/src/main.py`
- Modify: `backend/src/services/idea_service.py`
- Modify: `backend/src/tests/test_api_mvp.py`
- Modify: `backend/src/tests/test_idea_service.py`
- Modify after verification: `README.md`

### Task 4.1: Add API Endpoints

- [ ] **Step 1: Add API tests for candidate lifecycle**

Add to `backend/src/tests/test_api_mvp.py`:

```python
def test_memory_candidate_refresh_list_accept_and_semantic_list(tmp_path):
    test_db = tmp_path / "api-memory.sqlite3"
    store = get_memory_store(str(test_db))
    for _ in range(3):
        store.add_experiment_log_entry(
            {
                "task": "defect classification",
                "model": "1D-CNN",
                "dataset": "bearing fault dataset",
                "metric_problem": "minority PRAUC is low",
                "tried_methods": ["focal loss"],
                "observation": "recall improves but precision collapses",
                "goal": "improve PRAUC without making model too heavy",
                "tags": ["lightweight"],
            }
        )

    app.dependency_overrides[get_memory_store] = lambda: store
    client = TestClient(app)

    refresh = client.post("/memory/candidates/refresh")
    assert refresh.status_code == 200
    assert refresh.json()

    candidates = client.get("/memory/candidates")
    assert candidates.status_code == 200
    candidate_id = candidates.json()[0]["id"]

    accepted = client.post(f"/memory/candidates/{candidate_id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "confirmed"

    semantic = client.get("/memory/semantic")
    assert semantic.status_code == 200
    assert semantic.json()

    app.dependency_overrides.clear()
```

- [ ] **Step 2: Add API tests for reject and archive**

Add tests proving:

- `POST /memory/candidates/{candidate_id}/reject` returns `status="rejected"`
- rejected candidate does not create semantic memory
- `POST /memory/semantic/{memory_id}/archive` returns `status="archived"`
- archived semantic memory is omitted from default `GET /memory/semantic`

- [ ] **Step 3: Run failing API tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_api_mvp.py -q
```

Expected before implementation:

- New memory endpoint tests fail with 404.

- [ ] **Step 4: Wire API dependencies**

Add to `backend/src/main.py`:

```python
def get_memory_service(store: MemoryStore = Depends(get_memory_store)) -> MemoryService:
    return MemoryService(store=store, extractor=MemoryExtractor())
```

Add endpoint handlers matching the API contract draft:

- `GET /memory/candidates`
- `POST /memory/candidates/refresh`
- `POST /memory/candidates/{candidate_id}/accept`
- `POST /memory/candidates/{candidate_id}/reject`
- `GET /memory/semantic`
- `POST /memory/semantic/{memory_id}/archive`

Each handler should catch `MemoryServiceError` and convert it to `HTTPException`.

- [ ] **Step 5: Run API tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_api_mvp.py -q
```

Expected:

- Memory API tests pass.
- Existing API tests remain passing.

### Task 4.2: Add Confirmed Memory To Idea Assistant Context

- [ ] **Step 1: Add service test**

Add to `backend/src/tests/test_idea_service.py`:

```python
def test_idea_service_query_includes_confirmed_semantic_memory(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    candidate_id = store.upsert_memory_candidate(
        {
            "candidate_type": "semantic_proposal",
            "category": "user_preference",
            "subject": "user",
            "predicate": "prefers",
            "object": "lightweight",
            "summary": "User repeatedly prefers lightweight approaches.",
            "source_log_ids": [1, 2, 3],
            "evidence_count": 3,
            "score": 0.8,
            "status": "pending",
        }
    )
    store.upsert_semantic_memory_from_candidate(store.get_memory_candidate(candidate_id))
    service = IdeaRecommendationService(
        store=store,
        retrieval_service=FakeKnowledgeRetrievalService(),
        idea_generator=DeterministicIdeaGenerator(),
    )

    query = service.build_query(
        ExperimentLogRequest(
            task="defect classification",
            model="1D-CNN",
            dataset="bearing fault dataset",
            metric_problem="minority PRAUC is low",
            tried_methods=["focal loss"],
            observation="recall improves but precision collapses",
            goal="improve PRAUC",
            tags=[],
        )
    )

    assert "lightweight" in query
```

- [ ] **Step 2: Run failing idea test**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_idea_service.py::test_idea_service_query_includes_confirmed_semantic_memory -q
```

Expected before implementation:

- Fails because `IdeaRecommendationService.build_query()` only uses the current log.

- [ ] **Step 3: Extend idea query assembly**

Modify `IdeaRecommendationService.build_query()` so it:

- keeps current structured log as strongest context
- appends compact confirmed semantic memory from `store.build_memory_context()`
- does not append legacy `/logs`
- does not call external providers

Keep deterministic generator behavior and no-source fallback unchanged.

- [ ] **Step 4: Run idea tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_idea_service.py -q
```

Expected:

- Idea tests pass.

### Task 4.3: Minimal Stale/Conflict Review Contract

- [ ] **Step 1: Keep stale/conflict manual for MVP**

Do not implement automatic stale/conflict inference from time or vague evidence changes.

Allowed MVP behavior:

- `candidate_type="stale_proposal"` can be created only by explicit service/store call with source ids.
- `candidate_type="conflict_proposal"` can be created only by explicit service/store call with source ids.
- accepting a stale/conflict candidate should not silently mutate unrelated semantic memory unless the endpoint is explicitly designed and tested.

- [ ] **Step 2: Add tests that prevent automatic archive**

Add a test to `backend/src/tests/test_memory_service.py`:

```python
def test_refresh_candidates_does_not_archive_confirmed_memory_automatically(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    candidate_id = store.upsert_memory_candidate(
        {
            "candidate_type": "semantic_proposal",
            "category": "user_preference",
            "subject": "user",
            "predicate": "prefers",
            "object": "lightweight",
            "summary": "User repeatedly prefers lightweight approaches.",
            "source_log_ids": [1, 2, 3],
            "evidence_count": 3,
            "score": 0.8,
            "status": "pending",
        }
    )
    store.upsert_semantic_memory_from_candidate(store.get_memory_candidate(candidate_id))
    service = MemoryService(store=store, extractor=MemoryExtractor())

    service.refresh_candidates()

    assert store.list_semantic_memory()[0]["status"] == "confirmed"
```

- [ ] **Step 3: Run memory service tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_service.py -q
```

Expected:

- Confirmed memory is never archived by refresh.

### Task 4.4: README And Full Verification

- [ ] **Step 1: Run backend verification**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
```

Expected:

- All backend tests pass.

- [ ] **Step 2: Run import/startup smoke**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -c "from main import app; print(app.title)"
```

Expected:

- Imports FastAPI app without errors.

- [ ] **Step 3: Update README only after tests pass**

Document:

- `memory_candidates` are auto-suggested but review-gated.
- `semantic_memory` only becomes confirmed after user acceptance.
- query rewrite uses confirmed semantic memory plus recent 3 structured logs.
- stale/conflict are not automatically applied in MVP.
- Chroma/vector retrieval still only serves paper knowledge chunks.

Do not claim:

- automatic chat memory
- automatic stale/conflict resolution
- real provider verification
- graph/vector memory retrieval

- [ ] **Step 4: Run README claim scan**

Run:

```bash
rg -n "chat memory|自动保存|Neo4j|Qdrant|real|DeepSeek|OpenAI|confirmed|semantic_memory|memory_candidates|stale|conflict" README.md docs/superpowers/specs docs/superpowers/plans
```

Expected:

- Claims match implemented behavior.
- Any future-only features are clearly described as future work.

## Final Verification Checklist

- [ ] `PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_store.py -q`
- [ ] `PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_extractor.py -q`
- [ ] `PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_service.py -q`
- [ ] `PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_paper_discovery_graph.py -q`
- [ ] `PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_idea_service.py -q`
- [ ] `PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_api_mvp.py -q`
- [ ] `PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q`
- [ ] `PYTHONPATH=backend/src ./.venv/bin/python -c "from main import app; print(app.title)"`

## Suggested Execution Mode

Recommended default:

- Use `superpowers:subagent-driven-development`.
- Execute one phase at a time.
- Do not run multiple implementer subagents in parallel on shared files like `schemas.py`, `memory_store.py`, `main.py`, or `idea_service.py`.

Suggested cadence:

1. Implement Phase 1, then review context semantics.
2. Implement Phase 2, then review extraction quality and enum fit.
3. Implement Phase 3, then review confirmation/archiving semantics.
4. Implement Phase 4, then review API shape and README claims.

Learning-oriented alternative:

- The user manually reads and edits Phase 1 because it teaches the existing graph/query-rewrite path.
- Codex or subagents implement Phases 2-4 because they are more mechanical and test-heavy.

## Open Decisions Before Implementation

- Keep `category` and `predicate` enums exactly as the spec for MVP unless user says otherwise.
- Keep semantic proposal threshold at 3 global occurrences.
- Keep stale/conflict review-gated and not automatic.
- Keep `/logs` as legacy/simple notes and exclude it from query-rewrite memory context.
- Keep all real-provider and vector-memory work out of default tests.
