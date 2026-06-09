# Idea Assistant MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a backend-first Idea Assistant MVP that accepts structured experiment logs, retrieves local knowledge evidence, and returns 3-5 deterministic evidence-grounded idea options through `POST /ideas/recommend`.

**Architecture:** Keep the MVP as a thin service composition layer, not a chat memory system or planner. Add structured experiment log persistence in SQLite, reuse `KnowledgeRetrievalService` for evidence, add an idea-specific generator contract, and expose narrow FastAPI endpoints. Default execution remains deterministic and offline; DeepSeek/OpenAI paths are out of default pytest scope.

**Tech Stack:** FastAPI, Pydantic, SQLite `MemoryStore`, existing fake embedding/vector services, existing discovery graph dependency seam, pytest, Vue 3/Vite only as an optional final UI slice.

---

## Source Spec

Implement from:

- `docs/superpowers/specs/2026-06-09-idea-assistant-mvp-design.md`

This plan must not expand scope into:

- automatic conversation memory
- multi-turn chat memory
- Neo4j, Qdrant, or new vector infrastructure
- SSE
- production-grade agent planning
- default real DeepSeek/OpenAI calls
- frontend redesign

## File Map

Backend files to modify:

- `backend/src/services/schemas.py`
  - Add structured experiment log request/response schemas.
  - Add idea recommendation request/response schemas.

- `backend/src/services/memory_store.py`
  - Add `experiment_log_entries` table.
  - Add `add_experiment_log_entry()` and `list_experiment_log_entries()`.
  - Keep existing `/logs` methods unchanged.

- `backend/src/services/idea_service.py`
  - New file.
  - Define `IdeaServiceError`, `IdeaGenerator`, `DeterministicIdeaGenerator`, and `IdeaRecommendationService`.
  - Keep deterministic query building here.

- `backend/src/config.py`
  - Add future-facing idea provider config with deterministic defaults:
    - `idea_provider`
    - `idea_model`
    - `idea_temperature`
  - Do not wire real provider in the first backend MVP task unless the user explicitly asks.

- `backend/src/main.py`
  - Import new schemas and service.
  - Add dependency factory for deterministic idea generator.
  - Add `POST /experiments/logs`.
  - Add `GET /experiments/logs`.
  - Add `POST /ideas/recommend`.

Backend tests to modify/create:

- `backend/src/tests/test_memory_store.py`
  - Add structured experiment log persistence tests.

- `backend/src/tests/test_idea_service.py`
  - New file for generator and orchestration tests.

- `backend/src/tests/test_api_mvp.py`
  - Add endpoint tests.

Docs to modify:

- `README.md`
  - After implementation only, document completed endpoints and default deterministic behavior.

Optional frontend files:

- `frontend/src/api.js`
  - Add `createExperimentLog()`, `listExperimentLogs()`, `recommendIdeas()`.

- `frontend/src/components/IdeaAssistantPanel.vue`
  - Optional compact workbench panel.

- `frontend/src/components/ResearchWorkbench.vue`
  - Optional mount point for the panel.

## Review Gates

Subagents can execute:

- schema additions
- store methods
- deterministic generator
- service orchestration
- endpoint wiring
- tests
- README updates after implementation
- optional compact frontend panel

The user should personally review:

- structured experiment log field names
- `/logs` versus `/experiments/logs` boundary
- `/ideas/recommend` response contract
- no-source fallback behavior
- whether `include_discovery` should remain default `false`
- whether README wording avoids claiming real DeepSeek or real provider tests passed
- optional frontend information architecture

## Task 1: Structured Experiment Log Schema And Store

**Files:**

- Modify: `backend/src/services/schemas.py`
- Modify: `backend/src/services/memory_store.py`
- Test: `backend/src/tests/test_memory_store.py`

- [ ] **Step 1: Add failing schema/store tests**

Add these tests to `backend/src/tests/test_memory_store.py`:

```python
def test_initialize_creates_structured_experiment_log_entries_table(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    store = MemoryStore(str(db_path))

    store.initialize()

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    connection.close()

    assert "experiment_log_entries" in {row[0] for row in rows}


def test_add_structured_experiment_log_entry_can_be_listed(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    log_id = store.add_experiment_log_entry(
        {
            "task": "defect classification",
            "model": "1D-CNN",
            "dataset": "bearing fault dataset",
            "metric_problem": "minority class PRAUC is low",
            "tried_methods": ["class weighting", "focal loss"],
            "observation": "recall improves but precision collapses",
            "goal": "improve PRAUC without making model too heavy",
            "tags": ["imbalanced-learning", "lightweight"],
        }
    )

    logs = store.list_experiment_log_entries()

    assert log_id > 0
    assert logs[0]["id"] == log_id
    assert logs[0]["task"] == "defect classification"
    assert logs[0]["tried_methods"] == ["class weighting", "focal loss"]
    assert logs[0]["tags"] == ["imbalanced-learning", "lightweight"]
    assert logs[0]["created_at"]


def test_structured_experiment_logs_are_separate_from_legacy_logs(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    store.add_experiment_log("legacy note", tags=["block"])
    store.add_experiment_log_entry(
        {
            "task": "defect classification",
            "model": "1D-CNN",
            "dataset": "bearing fault dataset",
            "metric_problem": "minority class PRAUC is low",
            "tried_methods": [],
            "observation": "recall improves but precision collapses",
            "goal": "improve PRAUC without making model too heavy",
            "tags": [],
        }
    )

    assert store.list_experiment_logs()[0]["content"] == "legacy note"
    assert store.list_experiment_log_entries()[0]["task"] == "defect classification"
```

- [ ] **Step 2: Run failing store tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_store.py -q
```

Expected before implementation:

- Fails because `experiment_log_entries`, `add_experiment_log_entry()`, or `list_experiment_log_entries()` does not exist.

- [ ] **Step 3: Add Pydantic schemas**

Modify `backend/src/services/schemas.py`:

```python
class ExperimentLogRequest(BaseModel):
    task: str = Field(min_length=1)
    model: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    metric_problem: str = Field(min_length=1)
    tried_methods: list[str] = Field(default_factory=list)
    observation: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class ExperimentLogEntry(ExperimentLogRequest):
    id: int
    created_at: str


class ExperimentLogCreateResponse(BaseModel):
    id: int
    created_at: str
```

- [ ] **Step 4: Add SQLite table**

Modify `MemoryStore.initialize()` to create:

```sql
CREATE TABLE IF NOT EXISTS experiment_log_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT NOT NULL,
    model TEXT NOT NULL,
    dataset TEXT NOT NULL,
    metric_problem TEXT NOT NULL,
    tried_methods_json TEXT NOT NULL,
    observation TEXT NOT NULL,
    goal TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

- [ ] **Step 5: Add store methods**

Add methods to `MemoryStore`:

```python
def add_experiment_log_entry(self, entry: dict) -> int:
    now = self._now()
    with self._connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO experiment_log_entries (
                task,
                model,
                dataset,
                metric_problem,
                tried_methods_json,
                observation,
                goal,
                tags_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["task"],
                entry["model"],
                entry["dataset"],
                entry["metric_problem"],
                self._to_json(entry.get("tried_methods", [])),
                entry["observation"],
                entry["goal"],
                self._to_json(entry.get("tags", [])),
                now,
            ),
        )
        return int(cursor.lastrowid)


def list_experiment_log_entries(self, limit: int = 50) -> list[dict]:
    with self._connect() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                task,
                model,
                dataset,
                metric_problem,
                tried_methods_json,
                observation,
                goal,
                tags_json,
                created_at
            FROM experiment_log_entries
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "task": row["task"],
            "model": row["model"],
            "dataset": row["dataset"],
            "metric_problem": row["metric_problem"],
            "tried_methods": self._from_json(row["tried_methods_json"]),
            "observation": row["observation"],
            "goal": row["goal"],
            "tags": self._from_json(row["tags_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]
```

- [ ] **Step 6: Run store tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_memory_store.py -q
```

Expected after implementation:

- All `test_memory_store.py` tests pass.

**User review gate:** Confirm the structured log fields are sufficient for the resume project and do not need `baseline`, `constraints`, or `failure_mode` in this MVP.

## Task 2: Deterministic Idea Generator

**Files:**

- Create: `backend/src/services/idea_service.py`
- Modify: `backend/src/services/schemas.py`
- Test: `backend/src/tests/test_idea_service.py`

- [ ] **Step 1: Add idea response schemas**

Modify `backend/src/services/schemas.py`:

```python
class IdeaSupportingEvidence(BaseModel):
    source_type: Literal["knowledge", "discovery"]
    paper_id: str | None = None
    title: str | None = None
    chunk_index: int | None = None
    distance: float | None = None
    text: str | None = None
    vector_ref: str | None = None


class IdeaOption(BaseModel):
    title: str
    rationale: str
    supporting_evidence: list[IdeaSupportingEvidence] = Field(default_factory=list)
    expected_benefit: str
    risk: str
    suggested_validation_metric: str
    next_small_experiment: str
```

- [ ] **Step 2: Add failing generator tests**

Create `backend/src/tests/test_idea_service.py`:

```python
from services.idea_service import DeterministicIdeaGenerator
from services.schemas import ExperimentLogRequest, KnowledgeSearchResult


def make_log() -> ExperimentLogRequest:
    return ExperimentLogRequest(
        task="defect classification",
        model="1D-CNN",
        dataset="bearing fault dataset",
        metric_problem="minority class PRAUC is low",
        tried_methods=["class weighting", "focal loss"],
        observation="recall improves but precision collapses",
        goal="improve PRAUC without making model too heavy",
        tags=["imbalanced-learning"],
    )


def test_deterministic_idea_generator_returns_requested_count_with_knowledge_evidence():
    chunk = KnowledgeSearchResult(
        paper_id="paper-1",
        title="Imbalanced Fault Diagnosis",
        chunk_index=0,
        text="Precision-recall metrics are useful for imbalanced classification.",
        vector_ref="chroma:research_chunks:paper-1:0:hash",
        distance=0.1,
    )

    ideas = DeterministicIdeaGenerator().generate(
        experiment_log=make_log(),
        retrieved_chunks=[chunk],
        discovery_candidates=[],
        idea_count=3,
    )

    assert len(ideas) == 3
    assert all(idea.supporting_evidence for idea in ideas)
    assert ideas[0].supporting_evidence[0].source_type == "knowledge"
    assert ideas[0].supporting_evidence[0].paper_id == "paper-1"
    assert "PRAUC" in ideas[0].suggested_validation_metric


def test_deterministic_idea_generator_does_not_invent_evidence_without_sources():
    ideas = DeterministicIdeaGenerator().generate(
        experiment_log=make_log(),
        retrieved_chunks=[],
        discovery_candidates=[],
        idea_count=3,
    )

    assert len(ideas) == 3
    assert all(idea.supporting_evidence == [] for idea in ideas)
    assert "No local knowledge evidence" in ideas[0].rationale
```

- [ ] **Step 3: Run failing generator tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_idea_service.py -q
```

Expected before implementation:

- Fails because `services.idea_service` does not exist.

- [ ] **Step 4: Implement deterministic generator**

Create `backend/src/services/idea_service.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.schemas import (
    ExperimentLogRequest,
    IdeaOption,
    IdeaSupportingEvidence,
    KnowledgeSearchResult,
)


class IdeaServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class IdeaGenerator(Protocol):
    def generate(
        self,
        experiment_log: ExperimentLogRequest,
        retrieved_chunks: list[KnowledgeSearchResult],
        discovery_candidates: list[dict],
        idea_count: int,
    ) -> list[IdeaOption]:
        """Generate structured idea options from a structured experiment log and evidence."""


@dataclass
class DeterministicIdeaGenerator:
    def generate(
        self,
        experiment_log: ExperimentLogRequest,
        retrieved_chunks: list[KnowledgeSearchResult],
        discovery_candidates: list[dict],
        idea_count: int,
    ) -> list[IdeaOption]:
        evidence = self._knowledge_evidence(retrieved_chunks)
        rationale_prefix = (
            "Use the retrieved local knowledge evidence and the experiment log"
            if evidence
            else "No local knowledge evidence was found; use this as a conservative hypothesis from the experiment log"
        )
        templates = [
            IdeaOption(
                title="Tune a precision-aware decision threshold",
                rationale=f"{rationale_prefix} to separate representation learning from operating-point selection.",
                supporting_evidence=evidence[:1],
                expected_benefit=f"May improve {experiment_log.metric_problem} without changing the {experiment_log.model} architecture.",
                risk="Threshold tuning can overfit if the validation split is small or distribution-shifted.",
                suggested_validation_metric="minority-class PRAUC with a precision floor",
                next_small_experiment="Keep the trained checkpoint fixed and sweep decision thresholds on the validation split.",
            ),
            IdeaOption(
                title="Add a lightweight calibration step after imbalance training",
                rationale=f"{rationale_prefix} to test whether score calibration can reduce precision collapse.",
                supporting_evidence=evidence[:1],
                expected_benefit="May improve ranking quality and precision-recall tradeoffs with little inference overhead.",
                risk="Calibration may hide dataset leakage or become unstable on very small minority-class validation sets.",
                suggested_validation_metric="minority-class PRAUC plus expected calibration error",
                next_small_experiment="Fit a simple calibration layer on validation logits and compare PRAUC against the current focal-loss run.",
            ),
            IdeaOption(
                title="Use hard-negative focused sampling for the minority class",
                rationale=f"{rationale_prefix} to target false positives instead of only increasing recall.",
                supporting_evidence=evidence[:1],
                expected_benefit="May recover precision while preserving the recall gain from imbalance-aware training.",
                risk="Oversampling hard negatives can reduce generalization if the negatives are noisy or mislabeled.",
                suggested_validation_metric="minority-class PRAUC and precision at fixed recall",
                next_small_experiment="Run one training job that oversamples hard negatives from recent false-positive errors.",
            ),
            IdeaOption(
                title="Compare focal loss against class-balanced loss at fixed model size",
                rationale=f"{rationale_prefix} to isolate the loss-function effect from model capacity.",
                supporting_evidence=evidence[:1],
                expected_benefit="May improve minority ranking while keeping the model lightweight.",
                risk="Loss changes can improve one minority class while degrading macro behavior.",
                suggested_validation_metric="minority-class PRAUC, macro PRAUC, and parameter count",
                next_small_experiment="Train the same 1D-CNN with class-balanced loss and compare against focal loss using identical seeds.",
            ),
            IdeaOption(
                title="Audit minority-class label noise before adding capacity",
                rationale=f"{rationale_prefix} to check whether precision collapse comes from noisy labels or ambiguous windows.",
                supporting_evidence=evidence[:1],
                expected_benefit="May reveal a data issue that can be fixed without making the model heavier.",
                risk="Manual or heuristic auditing may be slow and can bias the validation process.",
                suggested_validation_metric="minority-class PRAUC before and after removing suspicious validation windows",
                next_small_experiment="Inspect the top false positives and false negatives, then rerun metrics after flagging ambiguous samples.",
            ),
        ]
        return templates[:idea_count]

    def _knowledge_evidence(self, chunks: list[KnowledgeSearchResult]) -> list[IdeaSupportingEvidence]:
        return [
            IdeaSupportingEvidence(
                source_type="knowledge",
                paper_id=chunk.paper_id,
                title=chunk.title,
                chunk_index=chunk.chunk_index,
                distance=chunk.distance,
                text=chunk.text,
                vector_ref=chunk.vector_ref,
            )
            for chunk in chunks
        ]
```

- [ ] **Step 5: Run generator tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_idea_service.py -q
```

Expected after implementation:

- Generator tests pass.

**User review gate:** Confirm deterministic idea text is conservative enough and does not overclaim evidence or expected benefit.

## Task 3: Idea Recommendation Orchestration

**Files:**

- Modify: `backend/src/services/idea_service.py`
- Modify: `backend/src/services/schemas.py`
- Test: `backend/src/tests/test_idea_service.py`

- [ ] **Step 1: Add recommendation schemas**

Modify `backend/src/services/schemas.py`:

```python
class IdeaRecommendRequest(BaseModel):
    experiment_log: ExperimentLogRequest
    save_log: bool = True
    include_discovery: bool = False
    top_k: int = Field(default=5, ge=1, le=20)
    idea_count: int = Field(default=3, ge=3, le=5)


class IdeaKnowledgeSection(BaseModel):
    sources: list[KnowledgeAnswerSource] = Field(default_factory=list)
    error: str | None = None


class IdeaDiscoverySection(BaseModel):
    enabled: bool
    candidates: list[dict] = Field(default_factory=list)
    error: str | None = None


class IdeaRecommendResponse(BaseModel):
    log_id: int | None = None
    query: str
    knowledge: IdeaKnowledgeSection
    discovery: IdeaDiscoverySection
    ideas: list[IdeaOption] = Field(default_factory=list)
    mode: str
```

- [ ] **Step 2: Add failing orchestration tests**

Append to `backend/src/tests/test_idea_service.py`:

```python
from services.idea_service import IdeaRecommendationService
from services.retrieval_service import KnowledgeRetrievalService
from services.embedding_service import FakeEmbeddingService
from services.memory_store import MemoryStore
from services.schemas import JudgeResult, PaperId, PaperMetadata
from services.vector_store import FakeVectorStoreService, build_chunk_uid


def make_judgement() -> JudgeResult:
    return JudgeResult(
        decision="accept",
        reason="Relevant",
        llm_relevance_score=0.9,
        embedding_relevance_score=0.8,
        quality_score=0.7,
        novelty_score=1.0,
        final_score=0.85,
        tags=["fake"],
    )


def seed_embedded_chunk(store: MemoryStore, vector_store: FakeVectorStoreService) -> None:
    paper = PaperMetadata(
        paper_id="paper-1",
        source_ids=PaperId(doi="10.1000/paper-1"),
        title="Imbalanced Fault Diagnosis",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi="10.1000/paper-1",
        source="test",
    )
    store.save_candidate_paper(paper, make_judgement())
    store.update_paper_status(paper.paper_id, "embedded", pdf_path="/tmp/paper-1.pdf")
    chunk_text = "Precision-recall metrics are useful for imbalanced classification."
    chunk_hash = "hash-0"
    chunk_uid = build_chunk_uid(paper.paper_id, 0, chunk_hash)
    vector_ref = vector_store.upsert_chunks(
        [{"chunk_uid": chunk_uid, "paper_id": paper.paper_id, "chunk_index": 0, "text": chunk_text}],
        embeddings=[FakeEmbeddingService().embed_texts([chunk_text])[0]],
    )[0]
    store.insert_knowledge_chunks(
        paper.paper_id,
        [{"chunk_index": 0, "text": chunk_text, "chunk_hash": chunk_hash, "vector_ref": vector_ref}],
    )


def build_recommendation_service(store: MemoryStore, vector_store: FakeVectorStoreService) -> IdeaRecommendationService:
    retrieval_service = KnowledgeRetrievalService(
        store=store,
        embedding_service=FakeEmbeddingService(),
        vector_store_service=vector_store,
    )
    return IdeaRecommendationService(
        store=store,
        retrieval_service=retrieval_service,
        idea_generator=DeterministicIdeaGenerator(),
        discovery_graph=None,
        mode="deterministic",
    )


def test_idea_recommendation_service_saves_log_retrieves_sources_and_returns_ideas(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    vector_store = FakeVectorStoreService()
    seed_embedded_chunk(store, vector_store)

    response = build_recommendation_service(store, vector_store).recommend(
        experiment_log=make_log(),
        save_log=True,
        include_discovery=False,
        top_k=5,
        idea_count=3,
    )

    assert response.log_id == 1
    assert "defect classification" in response.query
    assert response.knowledge.sources[0].paper_id == "paper-1"
    assert response.discovery.enabled is False
    assert len(response.ideas) == 3
    assert response.mode == "deterministic"


def test_idea_recommendation_service_can_return_no_source_fallback_without_saving_log(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    response = build_recommendation_service(store, FakeVectorStoreService()).recommend(
        experiment_log=make_log(),
        save_log=False,
        include_discovery=False,
        top_k=5,
        idea_count=3,
    )

    assert response.log_id is None
    assert response.knowledge.sources == []
    assert len(response.ideas) == 3
    assert store.list_experiment_log_entries() == []
```

- [ ] **Step 3: Run failing orchestration tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_idea_service.py -q
```

Expected before implementation:

- Fails because `IdeaRecommendationService` does not exist.

- [ ] **Step 4: Implement query builder and recommendation service**

Add to `backend/src/services/idea_service.py`:

```python
from services.retrieval_service import KnowledgeRetrievalService, RetrievalServiceError
from services.schemas import (
    IdeaDiscoverySection,
    IdeaKnowledgeSection,
    IdeaRecommendResponse,
    KnowledgeAnswerSource,
)


@dataclass
class IdeaRecommendationService:
    store: object
    retrieval_service: KnowledgeRetrievalService
    idea_generator: IdeaGenerator
    discovery_graph: object | None = None
    mode: str = "deterministic"

    def recommend(
        self,
        experiment_log: ExperimentLogRequest,
        save_log: bool = True,
        include_discovery: bool = False,
        top_k: int = 5,
        idea_count: int = 3,
    ) -> IdeaRecommendResponse:
        query = self.build_query(experiment_log)
        if not query:
            raise IdeaServiceError("experiment log produced an empty query", status_code=400)

        log_id = None
        if save_log:
            log_id = self.store.add_experiment_log_entry(experiment_log.model_dump())

        knowledge_sources: list[KnowledgeAnswerSource] = []
        knowledge_error = None
        retrieved_chunks = []
        try:
            retrieval_response = self.retrieval_service.search(query, top_k=top_k)
            retrieved_chunks = retrieval_response.results
            knowledge_sources = [
                KnowledgeAnswerSource(
                    paper_id=result.paper_id,
                    title=result.title,
                    chunk_index=result.chunk_index,
                    distance=result.distance,
                    text=result.text,
                    vector_ref=result.vector_ref,
                )
                for result in retrieved_chunks
            ]
        except RetrievalServiceError as exc:
            knowledge_error = exc.detail
            raise IdeaServiceError(exc.detail, status_code=exc.status_code) from exc

        discovery = IdeaDiscoverySection(enabled=include_discovery, candidates=[], error=None)
        if include_discovery and self.discovery_graph is not None:
            try:
                discovery_result = self.discovery_graph.invoke(
                    {
                        "mode": "basic",
                        "user_query": query,
                        "memory_context": "",
                        "rewritten_queries": [],
                        "raw_results": [],
                        "normalized_papers": [],
                        "deduped_papers": [],
                        "judge_results": [],
                        "ranked_candidates": [],
                    }
                )
                discovery.candidates = discovery_result["ranked_candidates"][:top_k]
            except Exception as exc:
                discovery.error = str(exc)

        ideas = self.idea_generator.generate(
            experiment_log=experiment_log,
            retrieved_chunks=retrieved_chunks,
            discovery_candidates=discovery.candidates,
            idea_count=idea_count,
        )

        return IdeaRecommendResponse(
            log_id=log_id,
            query=query,
            knowledge=IdeaKnowledgeSection(sources=knowledge_sources, error=knowledge_error),
            discovery=discovery,
            ideas=ideas,
            mode=self.mode,
        )

    def build_query(self, experiment_log: ExperimentLogRequest) -> str:
        parts = [
            experiment_log.task,
            experiment_log.model,
            experiment_log.dataset,
            experiment_log.metric_problem,
            experiment_log.observation,
            experiment_log.goal,
            " ".join(experiment_log.tried_methods),
        ]
        return " ".join(part.strip() for part in parts if part and part.strip())
```

- [ ] **Step 5: Run idea service tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_idea_service.py -q
```

Expected after implementation:

- All idea service tests pass.

**User review gate:** Confirm no-source fallback should return ideas instead of a hard failure.

## Task 4: FastAPI Endpoints

**Files:**

- Modify: `backend/src/main.py`
- Modify: `backend/src/config.py`
- Test: `backend/src/tests/test_api_mvp.py`

- [ ] **Step 1: Add failing API tests**

Append to `backend/src/tests/test_api_mvp.py`:

```python
def experiment_log_payload():
    return {
        "task": "defect classification",
        "model": "1D-CNN",
        "dataset": "bearing fault dataset",
        "metric_problem": "minority class PRAUC is low",
        "tried_methods": ["class weighting", "focal loss"],
        "observation": "recall improves but precision collapses",
        "goal": "improve PRAUC without making model too heavy",
        "tags": ["imbalanced-learning"],
    }


def test_experiment_logs_endpoint_saves_and_lists_structured_logs(tmp_path):
    test_db = tmp_path / "api-experiment-logs.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    client = TestClient(app)

    response = client.post("/experiments/logs", json=experiment_log_payload())
    assert response.status_code == 200
    assert response.json()["id"] == 1

    logs = client.get("/experiments/logs")
    assert logs.status_code == 200
    assert logs.json()[0]["task"] == "defect classification"
    assert logs.json()[0]["tried_methods"] == ["class weighting", "focal loss"]

    app.dependency_overrides.clear()


def test_ideas_recommend_endpoint_returns_deterministic_no_source_ideas(tmp_path):
    test_db = tmp_path / "api-ideas.sqlite3"
    store = get_memory_store(str(test_db))

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_store_service] = lambda: FakeVectorStoreService()
    client = TestClient(app)

    response = client.post(
        "/ideas/recommend",
        json={
            "experiment_log": experiment_log_payload(),
            "save_log": True,
            "include_discovery": False,
            "top_k": 5,
            "idea_count": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["log_id"] == 1
    assert body["mode"] == "deterministic"
    assert body["discovery"]["enabled"] is False
    assert len(body["ideas"]) == 3
    assert body["ideas"][0]["supporting_evidence"] == []

    app.dependency_overrides.clear()


def test_ideas_recommend_rejects_blank_required_fields(tmp_path):
    test_db = tmp_path / "api-ideas-invalid.sqlite3"
    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    client = TestClient(app)

    payload = experiment_log_payload()
    payload["task"] = ""

    response = client.post(
        "/ideas/recommend",
        json={"experiment_log": payload},
    )

    assert response.status_code == 422

    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run failing API tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_api_mvp.py -q
```

Expected before implementation:

- Fails because `/experiments/logs` and `/ideas/recommend` do not exist.

- [ ] **Step 3: Add idea config defaults**

Modify `backend/src/config.py`:

```python
idea_provider: str = "deterministic"
idea_model: str = "deepseek-chat"
idea_temperature: float = 0.0
```

And in `config = Config(...)`:

```python
idea_provider=os.getenv("IDEA_PROVIDER", "deterministic"),
idea_model=os.getenv("IDEA_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-chat")),
idea_temperature=float(os.getenv("IDEA_TEMPERATURE", "0")),
```

Do not call any real provider in this task.

- [ ] **Step 4: Wire dependencies and endpoints**

Modify imports in `backend/src/main.py` to include:

```python
from services.idea_service import DeterministicIdeaGenerator, IdeaGenerator, IdeaRecommendationService, IdeaServiceError
from services.schemas import (
    ExperimentLogCreateResponse,
    ExperimentLogEntry,
    ExperimentLogRequest,
    IdeaRecommendRequest,
)
```

Add dependency factories:

```python
def get_idea_generator() -> IdeaGenerator:
    if config.idea_provider == "deterministic":
        return DeterministicIdeaGenerator()
    raise ValueError(f"unsupported IDEA_PROVIDER: {config.idea_provider}")


def get_idea_mode() -> str:
    return config.idea_provider


def get_idea_recommendation_service(
    store: MemoryStore = Depends(get_memory_store),
    retrieval_service: KnowledgeRetrievalService = Depends(get_knowledge_retrieval_service),
    idea_generator: IdeaGenerator = Depends(get_idea_generator),
    discovery_graph=Depends(get_paper_discovery_graph),
) -> IdeaRecommendationService:
    return IdeaRecommendationService(
        store=store,
        retrieval_service=retrieval_service,
        idea_generator=idea_generator,
        discovery_graph=discovery_graph,
        mode=get_idea_mode(),
    )
```

Add endpoints:

```python
@app.post("/experiments/logs", response_model=ExperimentLogCreateResponse)
def add_experiment_log_entry(
    request: ExperimentLogRequest,
    store: MemoryStore = Depends(get_memory_store),
):
    log_id = store.add_experiment_log_entry(request.model_dump())
    entry = store.list_experiment_log_entries(limit=1)[0]
    return ExperimentLogCreateResponse(id=log_id, created_at=entry["created_at"])


@app.get("/experiments/logs", response_model=list[ExperimentLogEntry])
def list_experiment_log_entries(store: MemoryStore = Depends(get_memory_store)):
    return store.list_experiment_log_entries()


@app.post("/ideas/recommend")
def recommend_ideas(
    request: IdeaRecommendRequest,
    service: IdeaRecommendationService = Depends(get_idea_recommendation_service),
):
    try:
        return service.recommend(
            experiment_log=request.experiment_log,
            save_log=request.save_log,
            include_discovery=request.include_discovery,
            top_k=request.top_k,
            idea_count=request.idea_count,
        )
    except IdeaServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
```

- [ ] **Step 5: Run API tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_api_mvp.py -q
```

Expected after implementation:

- `test_api_mvp.py` passes.

**User review gate:** Confirm endpoint names are final enough to expose to the frontend.

## Task 5: End-To-End Backend Verification And README Update

**Files:**

- Modify: `README.md`
- Test command only: no new test file required unless a bug is found.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest \
  backend/src/tests/test_memory_store.py \
  backend/src/tests/test_idea_service.py \
  backend/src/tests/test_api_mvp.py \
  backend/src/tests/test_retrieval_service.py \
  -q
```

Expected:

- All selected tests pass.

- [ ] **Step 2: Run full backend tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
```

Expected:

- Full backend suite passes.

- [ ] **Step 3: Update README after tests pass**

Update `README.md` sections:

- `Implemented Endpoints`
  - Add `POST /experiments/logs`.
  - Add `GET /experiments/logs`.
  - Add `POST /ideas/recommend`.

- `Persistence`
  - Add `experiment_log_entries`.
  - Keep `experiment_logs` described as legacy/simple logs.

- Add a short `Idea Assistant MVP` section:

```markdown
## Idea Assistant MVP

The backend now supports a deterministic Idea Assistant MVP:

- `POST /experiments/logs` stores structured experiment logs.
- `GET /experiments/logs` lists structured experiment logs.
- `POST /ideas/recommend` builds a retrieval query from one structured log, searches local embedded knowledge chunks, and returns 3-5 structured idea options.

Default behavior is deterministic and offline. The endpoint does not call DeepSeek, OpenAI, BGE-M3, Chroma, arXiv, or OpenAlex unless future explicit provider configuration and manual smoke steps are added.

Idea `supporting_evidence` comes only from retrieval/discovery objects. The generator must not invent papers, chunks, citations, or source details.
```

Do not write that real DeepSeek idea generation has passed unless a separate manual smoke was actually run.

- [ ] **Step 4: Verify README wording**

Run:

```bash
rg -n "DeepSeek|OpenAI|BGE-M3|Chroma|ideas/recommend|experiments/logs|implemented|completed|passed" README.md
```

Expected:

- README describes completed deterministic behavior only.
- README does not claim real provider idea generation has passed.

**User review gate:** Confirm README wording is resume-safe and does not overclaim.

## Task 6: Optional Frontend Workbench Slice

Only start this task after the backend API contract passes and the user confirms a frontend slice is desired.

**Files:**

- Modify: `frontend/src/api.js`
- Create: `frontend/src/components/IdeaAssistantPanel.vue`
- Modify: `frontend/src/components/ResearchWorkbench.vue`
- Test: add or update component tests under `frontend/src/components/__tests__/` if the local frontend test setup remains stable.

- [ ] **Step 1: Add API helper functions**

Modify `frontend/src/api.js`:

```javascript
export function createExperimentLog(payload) {
  return request("/experiments/logs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function listExperimentLogs() {
  return request("/experiments/logs");
}

export function recommendIdeas(payload) {
  return request("/ideas/recommend", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}
```

- [ ] **Step 2: Build compact panel**

Create `frontend/src/components/IdeaAssistantPanel.vue` as a dense workbench panel with:

- structured inputs for `task`, `model`, `dataset`, `metric_problem`, `tried_methods`, `observation`, `goal`
- `save_log` checkbox
- `include_discovery` checkbox default off
- `idea_count` selector for 3-5
- submit button
- ideas list showing title, rationale, expected benefit, risk, metric, next small experiment
- evidence list per idea
- discovery error display if present

Do not build a landing page or chat UI.

- [ ] **Step 3: Mount panel in workbench**

Modify `frontend/src/components/ResearchWorkbench.vue` to include the panel without replacing existing discovery/knowledge workflow.

- [ ] **Step 4: Run frontend checks**

Run:

```bash
cd frontend
npm run build
```

If frontend tests are configured:

```bash
cd frontend
npm test -- --run
```

Expected:

- Build passes.
- Tests pass if test script exists and dependencies are installed.

**User review gate:** Confirm the panel still feels like a workbench and does not become a marketing page or a multi-turn assistant.

## Final Verification Checklist

Before claiming implementation complete, run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
```

If frontend task was implemented, also run:

```bash
cd frontend
npm run build
```

Manual real-provider smoke is explicitly out of default completion criteria:

- no real DeepSeek idea provider smoke required
- no real OpenAI idea provider smoke required
- no real BGE-M3 smoke required
- no real Chroma smoke required
- no real arXiv/OpenAlex smoke required

If a future task adds `IDEA_PROVIDER=deepseek`, write a separate manual smoke plan and keep default pytest deterministic.

## Execution Choice

Plan complete once this file is reviewed. Two execution options:

1. Subagent-Driven (recommended): dispatch a fresh subagent per task, review between tasks, fastest clean iteration.
2. Inline Execution: execute tasks in this session with checkpoints.

Recommended path:

- Use Subagent-Driven for Tasks 1-5.
- Defer Task 6 until the backend API is accepted.
