# Research Management MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable research-management MVP: Basic paper discovery, candidate ranking, local persistence, Advanced-lite query rewriting, manual PDF upload, vector-store ingestion, and a simple Vue workbench.

**Architecture:** Keep the existing Python service layout and turn it into a working FastAPI + LangGraph backend. Start with a REST-only synchronous flow, persist state in SQLite, store uploaded PDFs locally, and postpone SSE until after the MVP closes the loop.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, Pydantic, SQLite, pytest, arXiv/OpenAlex adapters, local vector store with Chroma, Vue 3 + Vite.

---

## Scope

This plan implements the MVP approved in `docs/superpowers/specs/2026-06-07-research-management-mvp-design.md`.

SSE, full async task queues, automatic PDF download, multi-user auth, full paper QA, and complex multi-agent research planning are deliberately excluded from this plan.

## File Map

### Backend Files To Modify

- `pyproject.toml`
  - Add runtime dependencies needed by the MVP: FastAPI, Uvicorn, requests if missing, PDF parsing, and one vector-store option.

- `backend/src/main.py`
  - Replace the current LangGraph scratch script with a real FastAPI app.
  - Expose REST endpoints for search, candidates, logs, upload, and memory summary.

- `backend/src/config.py`
  - Add local paths for SQLite database, PDF upload directory, and vector database directory.

- `backend/src/services/schemas.py`
  - Add API request/response models and persisted paper status fields.
  - Keep existing `PaperMetadata`, `PaperId`, and `JudgeResult` as the core paper models.

- `backend/src/services/scoreutils.py`
  - Fix imports so tests can run from the current package layout.

- `backend/src/services/LlmPaperSelect.py`
  - Fix final-score calculation to call `ScoreUtils.calculate_final_score`.
  - Keep mock judge behavior until the flow is stable.

- `backend/src/services/deduplicator.py`
  - Keep DOI normalization.
  - Change the source of known DOI data to the persistence layer once `memory_store` exists.

- `backend/src/graph/state.py`
  - Replace the narrow paper-select state with the MVP discovery state.

- `backend/src/graph/nodes.py`
  - Add nodes for memory loading, query rewriting, search, dedup, judge, rank, and candidate persistence.

- `backend/src/graph/builder.py`
  - Build `paper_discovery_graph` with names that match `nodes.py`.

### Backend Files To Create

- `backend/src/services/memory_store.py`
  - SQLite setup and CRUD for conversations, experiment logs, papers, judgements, and knowledge chunks.

- `backend/src/services/knowledge_base.py`
  - Save uploaded PDFs, extract text, chunk text, create embeddings, and write chunks to local vector storage.

- `backend/src/tests/test_scoreutils.py`
  - Unit tests for final score and novelty score.

- `backend/src/tests/test_deduplicator.py`
  - Unit tests for DOI normalization and uploaded/embedded-only dedup behavior.

- `backend/src/tests/test_memory_store.py`
  - Unit tests for SQLite persistence.

- `backend/src/tests/test_paper_discovery_graph.py`
  - Graph-level test with fake search, fake judge, and in-memory SQLite.

- `backend/src/tests/test_api_mvp.py`
  - FastAPI tests for search, logs, candidates, and upload stubs.

### Frontend Files To Create

- `frontend/package.json`
  - Vite + Vue setup.

- `frontend/src/main.js`
  - Vue bootstrap.

- `frontend/src/App.vue`
  - Simple workbench shell.

- `frontend/src/api.js`
  - Backend API client.

- `frontend/src/components/SearchWorkbench.vue`
  - Basic / Advanced-lite search UI and candidate table.

- `frontend/src/components/ExperimentLogs.vue`
  - Experiment log input and history.

- `frontend/src/components/KnowledgeBase.vue`
  - Uploaded/embedded papers list.

---

## Task 1: Make Current Backend Importable And Testable

**Files:**
- Modify: `backend/src/services/scoreutils.py`
- Modify: `backend/src/services/LlmPaperSelect.py`
- Modify: `backend/src/graph/builder.py`
- Modify: `backend/src/graph/nodes.py`
- Modify: `backend/src/graph/state.py`
- Create: `backend/src/tests/test_scoreutils.py`
- Create: `backend/src/tests/test_llm_judge.py`

- [ ] **Step 1: Write score utility tests**

Create `backend/src/tests/test_scoreutils.py`:

```python
from services.scoreutils import ScoreUtils
from services.schemas import PaperId, PaperMetadata


def test_calculate_final_score_uses_expected_weights():
    score = ScoreUtils.calculate_final_score(
        llm_relevance_score=0.7,
        embedding_relevance_score=0.65,
        quality_score=0.6,
        novelty_score=0.5,
    )

    assert score == 0.595


def test_calculate_novelty_score_for_current_year_paper():
    paper = PaperMetadata(
        paper_id="p1",
        source_ids=PaperId(doi="10.1000/test"),
        title="Recent Paper",
        authors=[],
        abstract="A recent paper.",
        published_date="2026-01-01",
        source="test",
    )

    assert ScoreUtils.calculate_novelty_score(paper, current_year=2026) == 1.0
```

- [ ] **Step 2: Write LLM judge tests**

Create `backend/src/tests/test_llm_judge.py`:

```python
from services.LlmPaperSelect import LLMJudge
from services.schemas import PaperId, PaperMetadata


def test_judge_marks_missing_abstract_as_uncertain():
    judge = LLMJudge()
    paper = PaperMetadata(
        paper_id="p1",
        source_ids=PaperId(),
        title="Missing Abstract",
        authors=[],
        abstract=None,
        source="test",
    )

    result = judge.judge(paper)

    assert result.decision == "uncertain"
    assert "missing_abstract" in result.tags


def test_judge_returns_sorted_results_by_final_score():
    judge = LLMJudge()
    paper = PaperMetadata(
        paper_id="p2",
        source_ids=PaperId(doi="10.1000/has-abstract"),
        title="Has Abstract",
        authors=[],
        abstract="This paper has enough text for a mock judgement.",
        source="test",
    )

    result = judge.judge(paper)

    assert result.decision == "accept"
    assert result.final_score > 0
```

- [ ] **Step 3: Run tests to verify current failures**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_scoreutils.py backend/src/tests/test_llm_judge.py -v
```

Expected before implementation:

- `test_scoreutils.py` may fail because `scoreutils.py` imports `schemas` instead of `services.schemas`.
- `test_llm_judge.py` may fail because `LLMJudge` calls `self.calculate_final_score`, which is not defined.

- [ ] **Step 4: Fix imports and score calculation**

Modify `backend/src/services/scoreutils.py` so the import uses the existing package path:

```python
from services.schemas import PaperMetadata
```

Modify `backend/src/services/LlmPaperSelect.py` so final scores call:

```python
ScoreUtils.calculate_final_score(
    llm_relevance_score=llm_relevance_score,
    embedding_relevance_score=embedding_relevance_score,
    quality_score=quality_score,
    novelty_score=novelty_score,
)
```

- [ ] **Step 5: Temporarily align graph names so imports do not break**

Modify `backend/src/graph/nodes.py` to expose a single working node:

```python
def paper_select_node(state: PaperSelectState) -> PaperSelectState:
    deduplicator = DeDuplicator()
    new_papers = deduplicator.dedup(state["papers"])
    judge = LLMJudge()
    state["judge_results"] = judge.sort_by_final_score(
        [judge.judge(paper) for paper in new_papers]
    )
    return state
```

Modify `backend/src/graph/builder.py` to use that node:

```python
from langgraph.graph import END, START, StateGraph

from graph.nodes import paper_select_node
from graph.state import PaperSelectState


def build_paper_select_graph():
    builder = StateGraph(PaperSelectState)
    builder.add_node("paper_select", paper_select_node)
    builder.add_edge(START, "paper_select")
    builder.add_edge("paper_select", END)
    return builder.compile()
```

- [ ] **Step 6: Run tests to verify pass**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_scoreutils.py backend/src/tests/test_llm_judge.py -v
```

Expected: both files pass.

- [ ] **Step 7: Commit**

```bash
git add backend/src/services/scoreutils.py backend/src/services/LlmPaperSelect.py backend/src/graph/builder.py backend/src/graph/nodes.py backend/src/graph/state.py backend/src/tests/test_scoreutils.py backend/src/tests/test_llm_judge.py
git commit -m "test: stabilize paper scoring and judge"
```

---

## Task 2: Add SQLite Memory Store

**Files:**
- Modify: `backend/src/config.py`
- Create: `backend/src/services/memory_store.py`
- Create: `backend/src/tests/test_memory_store.py`

- [ ] **Step 1: Add config fields**

Modify `backend/src/config.py` by adding fields to `Config`:

```python
database_path: str = "backend/data/research_memory.sqlite3"
pdf_upload_dir: str = "backend/data/uploads"
vector_store_dir: str = "backend/data/vector_store"
```

Add environment overrides in the `config = Config(...)` call:

```python
database_path=os.getenv("DATABASE_PATH", "backend/data/research_memory.sqlite3"),
pdf_upload_dir=os.getenv("PDF_UPLOAD_DIR", "backend/data/uploads"),
vector_store_dir=os.getenv("VECTOR_STORE_DIR", "backend/data/vector_store"),
```

- [ ] **Step 2: Write memory-store tests**

Create `backend/src/tests/test_memory_store.py`:

```python
from services.memory_store import MemoryStore
from services.schemas import JudgeResult, PaperId, PaperMetadata


def test_memory_store_saves_logs_candidates_and_known_dois(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    store = MemoryStore(str(db_path))
    store.initialize()

    log_id = store.add_experiment_log("training loss is unstable", tags=["block"])

    paper = PaperMetadata(
        paper_id="p1",
        source_ids=PaperId(doi="10.1000/test"),
        title="A Test Paper",
        authors=["Tester"],
        abstract="Test abstract",
        published_date="2026-01-01",
        doi="10.1000/test",
        source="test",
    )
    judgement = JudgeResult(
        decision="accept",
        reason="Good fit",
        llm_relevance_score=0.9,
        embedding_relevance_score=0.8,
        quality_score=0.7,
        novelty_score=1.0,
        final_score=0.85,
        tags=["useful"],
    )

    store.save_candidate_paper(paper, judgement)
    candidates = store.list_candidate_papers()

    assert log_id > 0
    assert candidates[0]["paper_id"] == "p1"
    assert store.list_known_dois() == []

    store.update_paper_status("p1", "uploaded", pdf_path="/tmp/p1.pdf")

    assert store.list_known_dois() == ["10.1000/test"]
```

- [ ] **Step 3: Run test to verify failure**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_memory_store.py -v
```

Expected: FAIL because `services.memory_store` does not exist.

- [ ] **Step 4: Implement `MemoryStore`**

Create `backend/src/services/memory_store.py` with a `MemoryStore` class that exposes these public methods:

- `__init__(database_path: str)`
- `initialize() -> None`
- `add_conversation(role: str, content: str) -> int`
- `add_experiment_log(content: str, tags: list[str] | None = None) -> int`
- `list_experiment_logs(limit: int = 50) -> list[dict]`
- `save_candidate_paper(paper: PaperMetadata, judgement: JudgeResult | None = None) -> None`
- `list_candidate_papers(limit: int = 100) -> list[dict]`
- `update_paper_status(paper_id: str, status: str, pdf_path: str | None = None) -> None`
- `list_known_dois() -> list[str]`

Implementation rules:

- Use only Python standard-library `sqlite3`, `json`, `datetime`, and `pathlib`.
- Create tables in `initialize()`.
- Store list/dict fields as JSON text.
- Normalize DOI to lowercase and strip `https://doi.org/`.
- `list_known_dois()` returns DOI values only for papers with status `uploaded`, `chunked`, or `embedded`.
- Use `INSERT OR REPLACE` for paper metadata keyed by `paper_id`.

- [ ] **Step 5: Run memory-store test**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_memory_store.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/config.py backend/src/services/memory_store.py backend/src/tests/test_memory_store.py
git commit -m "feat: add sqlite memory store"
```

---

## Task 3: Move DOI Dedup To Persisted Uploaded Papers

**Files:**
- Modify: `backend/src/services/deduplicator.py`
- Create: `backend/src/tests/test_deduplicator.py`

- [ ] **Step 1: Write dedup tests**

Create `backend/src/tests/test_deduplicator.py`:

```python
from services.deduplicator import DeDuplicator
from services.memory_store import MemoryStore
from services.schemas import PaperId, PaperMetadata


def make_paper(paper_id: str, doi: str | None) -> PaperMetadata:
    return PaperMetadata(
        paper_id=paper_id,
        source_ids=PaperId(doi=doi),
        title=f"Paper {paper_id}",
        authors=[],
        abstract="abstract",
        doi=doi,
        source="test",
    )


def test_dedup_only_filters_uploaded_or_embedded_dois(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    candidate = make_paper("candidate", "10.1000/candidate")
    uploaded = make_paper("uploaded", "10.1000/uploaded")
    store.save_candidate_paper(candidate)
    store.save_candidate_paper(uploaded)
    store.update_paper_status("uploaded", "uploaded", pdf_path="/tmp/uploaded.pdf")

    deduplicator = DeDuplicator(known_dois=store.list_known_dois())
    result = deduplicator.dedup([
        make_paper("new", "10.1000/new"),
        make_paper("candidate-copy", "10.1000/candidate"),
        make_paper("uploaded-copy", "https://doi.org/10.1000/UPLOADED"),
    ])

    assert [paper.paper_id for paper in result] == ["new", "candidate-copy"]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_deduplicator.py -v
```

Expected: FAIL because `DeDuplicator` does not accept `known_dois`.

- [ ] **Step 3: Update `DeDuplicator` constructor**

Modify `backend/src/services/deduplicator.py` so the constructor accepts either a provided DOI list or the legacy JSON path:

```python
class DeDuplicator:
    def __init__(
        self,
        storage_path: str = "data/known_papers.json",
        known_dois: list[str] | set[str] | None = None,
    ):
        self.storage_path = Path(storage_path)
        self.known_dois: set[str] = set()
        if known_dois is not None:
            self.known_dois = {
                doi for doi in (self._normalize_doi(value) for value in known_dois) if doi
            }
        else:
            self._load_known_papers()
```

Keep `register()` for backward compatibility, but the graph should use `MemoryStore.list_known_dois()` instead of registering during dedup.

- [ ] **Step 4: Run dedup tests**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_deduplicator.py -v
```

Expected: PASS.

- [ ] **Step 5: Run related tests**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_memory_store.py backend/src/tests/test_deduplicator.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/services/deduplicator.py backend/src/tests/test_deduplicator.py
git commit -m "feat: deduplicate against uploaded papers"
```

---

## Task 4: Build Basic Paper Discovery Graph

**Files:**
- Modify: `backend/src/graph/state.py`
- Modify: `backend/src/graph/nodes.py`
- Modify: `backend/src/graph/builder.py`
- Create: `backend/src/tests/test_paper_discovery_graph.py`

- [ ] **Step 1: Write graph test with fake services**

Create `backend/src/tests/test_paper_discovery_graph.py`:

```python
from graph.builder import build_paper_discovery_graph
from services.memory_store import MemoryStore
from services.schemas import JudgeResult, PaperId, PaperMetadata


class FakeSearchService:
    def search(self, query: str) -> list[PaperMetadata]:
        return [
            PaperMetadata(
                paper_id="p1",
                source_ids=PaperId(doi="10.1000/p1"),
                title=f"Paper for {query}",
                authors=["Tester"],
                abstract="Useful abstract.",
                doi="10.1000/p1",
                source="test",
            )
        ]


class FakeJudge:
    def judge(self, paper: PaperMetadata) -> JudgeResult:
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

    def sort_by_final_score(self, results: list[JudgeResult]) -> list[JudgeResult]:
        return sorted(results, key=lambda item: item.final_score, reverse=True)


def test_basic_paper_discovery_graph_persists_candidates(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    graph = build_paper_discovery_graph(
        search_service=FakeSearchService(),
        judge=FakeJudge(),
        memory_store=store,
    )

    result = graph.invoke({
        "mode": "basic",
        "user_query": "graph reconstruction",
        "memory_context": "",
        "rewritten_queries": [],
        "raw_results": [],
        "normalized_papers": [],
        "deduped_papers": [],
        "judge_results": [],
        "ranked_candidates": [],
    })

    assert result["rewritten_queries"] == ["graph reconstruction"]
    assert result["ranked_candidates"][0]["paper"].paper_id == "p1"
    assert store.list_candidate_papers()[0]["paper_id"] == "p1"
```

- [ ] **Step 2: Run graph test to verify failure**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_paper_discovery_graph.py -v
```

Expected: FAIL because `build_paper_discovery_graph` does not exist.

- [ ] **Step 3: Replace state with discovery state**

Modify `backend/src/graph/state.py`:

```python
from typing import Literal, TypedDict

from services.schemas import JudgeResult, PaperMetadata


class RankedCandidate(TypedDict):
    paper: PaperMetadata
    judgement: JudgeResult


class PaperDiscoveryState(TypedDict):
    mode: Literal["basic", "advanced"]
    user_query: str
    memory_context: str
    rewritten_queries: list[str]
    raw_results: list[PaperMetadata]
    normalized_papers: list[PaperMetadata]
    deduped_papers: list[PaperMetadata]
    judge_results: list[JudgeResult]
    ranked_candidates: list[RankedCandidate]
```

- [ ] **Step 4: Implement graph node factory**

Modify `backend/src/graph/nodes.py` to use dependency injection:

```python
from services.deduplicator import DeDuplicator
from services.LlmPaperSelect import LLMJudge
from services.memory_store import MemoryStore
from services.paper_search import PaperSearchService
from graph.state import PaperDiscoveryState


def make_nodes(
    search_service: PaperSearchService,
    judge: LLMJudge,
    memory_store: MemoryStore,
):
    def load_memory_context(state: PaperDiscoveryState) -> dict:
        return {"memory_context": ""}

    def rewrite_query(state: PaperDiscoveryState) -> dict:
        return {"rewritten_queries": [state["user_query"]]}

    def multi_source_search(state: PaperDiscoveryState) -> dict:
        papers = []
        for query in state["rewritten_queries"]:
            papers.extend(search_service.search(query))
        return {"raw_results": papers, "normalized_papers": papers}

    def dedup_papers(state: PaperDiscoveryState) -> dict:
        deduplicator = DeDuplicator(known_dois=memory_store.list_known_dois())
        return {"deduped_papers": deduplicator.dedup(state["normalized_papers"])}

    def judge_papers(state: PaperDiscoveryState) -> dict:
        return {"judge_results": [judge.judge(paper) for paper in state["deduped_papers"]]}

    def rank_papers(state: PaperDiscoveryState) -> dict:
        sorted_judgements = judge.sort_by_final_score(state["judge_results"])
        by_index = []
        for paper, judgement in zip(state["deduped_papers"], state["judge_results"], strict=False):
            by_index.append({"paper": paper, "judgement": judgement})
        by_index.sort(key=lambda item: item["judgement"].final_score, reverse=True)
        return {"judge_results": sorted_judgements, "ranked_candidates": by_index}

    def persist_candidates(state: PaperDiscoveryState) -> dict:
        for item in state["ranked_candidates"]:
            memory_store.save_candidate_paper(item["paper"], item["judgement"])
        return {}

    return {
        "load_memory_context": load_memory_context,
        "rewrite_query": rewrite_query,
        "multi_source_search": multi_source_search,
        "dedup_papers": dedup_papers,
        "judge_papers": judge_papers,
        "rank_papers": rank_papers,
        "persist_candidates": persist_candidates,
    }
```

- [ ] **Step 5: Implement graph builder**

Modify `backend/src/graph/builder.py`:

```python
from langgraph.graph import END, START, StateGraph

from graph.nodes import make_nodes
from graph.state import PaperDiscoveryState
from services.LlmPaperSelect import LLMJudge
from services.memory_store import MemoryStore
from services.paper_search import PaperSearchService


def build_paper_discovery_graph(
    search_service: PaperSearchService | None = None,
    judge: LLMJudge | None = None,
    memory_store: MemoryStore | None = None,
):
    if memory_store is None:
        raise ValueError("memory_store is required")

    nodes = make_nodes(
        search_service=search_service or PaperSearchService(),
        judge=judge or LLMJudge(),
        memory_store=memory_store,
    )

    builder = StateGraph(PaperDiscoveryState)
    for name, node in nodes.items():
        builder.add_node(name, node)

    builder.add_edge(START, "load_memory_context")
    builder.add_edge("load_memory_context", "rewrite_query")
    builder.add_edge("rewrite_query", "multi_source_search")
    builder.add_edge("multi_source_search", "dedup_papers")
    builder.add_edge("dedup_papers", "judge_papers")
    builder.add_edge("judge_papers", "rank_papers")
    builder.add_edge("rank_papers", "persist_candidates")
    builder.add_edge("persist_candidates", END)

    return builder.compile()
```

- [ ] **Step 6: Run graph test**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_paper_discovery_graph.py -v
```

Expected: PASS.

- [ ] **Step 7: Run backend unit tests**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_scoreutils.py backend/src/tests/test_llm_judge.py backend/src/tests/test_memory_store.py backend/src/tests/test_deduplicator.py backend/src/tests/test_paper_discovery_graph.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/src/graph/state.py backend/src/graph/nodes.py backend/src/graph/builder.py backend/src/tests/test_paper_discovery_graph.py
git commit -m "feat: add basic paper discovery graph"
```

---

## Task 5: Add FastAPI REST MVP

**Files:**
- Modify: `pyproject.toml`
- Modify: `backend/src/services/schemas.py`
- Modify: `backend/src/main.py`
- Create: `backend/src/tests/test_api_mvp.py`

- [ ] **Step 1: Add dependencies**

Modify `pyproject.toml` dependencies:

```toml
"fastapi>=0.115.0",
"uvicorn>=0.32.0",
"python-multipart>=0.0.12",
"requests>=2.32.0",
```

- [ ] **Step 2: Add API schemas**

Modify `backend/src/services/schemas.py` by adding:

```python
class SearchRequest(BaseModel):
    mode: Literal["basic", "advanced"] = "basic"
    query: str


class LogRequest(BaseModel):
    content: str
    tags: list[str] = []


class AcceptPaperRequest(BaseModel):
    paper_id: str
```

- [ ] **Step 3: Write API tests**

Create `backend/src/tests/test_api_mvp.py`:

```python
from fastapi.testclient import TestClient

from main import app, get_memory_store


def test_logs_endpoint_saves_and_lists_logs(tmp_path):
    test_db = tmp_path / "api.sqlite3"
    app.dependency_overrides[get_memory_store] = lambda: get_memory_store(str(test_db))
    client = TestClient(app)

    response = client.post("/logs", json={"content": "loss exploded", "tags": ["block"]})
    assert response.status_code == 200

    logs = client.get("/logs")
    assert logs.status_code == 200
    assert logs.json()[0]["content"] == "loss exploded"

    app.dependency_overrides.clear()


def test_candidates_endpoint_returns_empty_list(tmp_path):
    test_db = tmp_path / "api.sqlite3"
    app.dependency_overrides[get_memory_store] = lambda: get_memory_store(str(test_db))
    client = TestClient(app)

    response = client.get("/papers/candidates")

    assert response.status_code == 200
    assert response.json() == []

    app.dependency_overrides.clear()
```

- [ ] **Step 4: Run API tests to verify failure**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_api_mvp.py -v
```

Expected: FAIL because `main.py` is not a FastAPI app.

- [ ] **Step 5: Replace `main.py` with FastAPI app**

Modify `backend/src/main.py` to expose these functions and endpoints:

```python
from fastapi import Depends, FastAPI

from config import config
from graph.builder import build_paper_discovery_graph
from services.memory_store import MemoryStore
from services.schemas import LogRequest, SearchRequest


app = FastAPI(title="Research Management MVP")


def get_memory_store(database_path: str | None = None) -> MemoryStore:
    store = MemoryStore(database_path or config.database_path)
    store.initialize()
    return store


@app.post("/search")
def search(request: SearchRequest, store: MemoryStore = Depends(get_memory_store)):
    graph = build_paper_discovery_graph(memory_store=store)
    result = graph.invoke({
        "mode": request.mode,
        "user_query": request.query,
        "memory_context": "",
        "rewritten_queries": [],
        "raw_results": [],
        "normalized_papers": [],
        "deduped_papers": [],
        "judge_results": [],
        "ranked_candidates": [],
    })
    return result["ranked_candidates"]


@app.get("/papers/candidates")
def list_candidates(store: MemoryStore = Depends(get_memory_store)):
    return store.list_candidate_papers()


@app.post("/logs")
def add_log(request: LogRequest, store: MemoryStore = Depends(get_memory_store)):
    log_id = store.add_experiment_log(request.content, request.tags)
    return {"id": log_id}


@app.get("/logs")
def list_logs(store: MemoryStore = Depends(get_memory_store)):
    return store.list_experiment_logs()


@app.get("/memory/summary")
def memory_summary(store: MemoryStore = Depends(get_memory_store)):
    return {
        "candidate_count": len(store.list_candidate_papers()),
        "known_dois": store.list_known_dois(),
        "recent_logs": store.list_experiment_logs(limit=5),
    }
```

- [ ] **Step 6: Run API tests**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_api_mvp.py -v
```

Expected: PASS.

- [ ] **Step 7: Run local app smoke test**

Run:

```bash
PYTHONPATH=backend/src uvicorn main:app --app-dir backend/src --port 8000
```

In another terminal, run:

```bash
curl -s http://127.0.0.1:8000/memory/summary
```

Expected: JSON with `candidate_count`, `known_dois`, and `recent_logs`.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml backend/src/services/schemas.py backend/src/main.py backend/src/tests/test_api_mvp.py
git commit -m "feat: add research management api"
```

---

## Task 6: Add Advanced-lite Query Rewriting

**Files:**
- Modify: `backend/src/services/memory_store.py`
- Create: `backend/src/services/query_rewriter.py`
- Modify: `backend/src/graph/nodes.py`
- Modify: `backend/src/graph/builder.py`
- Create: `backend/src/tests/test_query_rewriter.py`
- Modify: `backend/src/tests/test_paper_discovery_graph.py`

- [ ] **Step 1: Write query rewriter tests**

Create `backend/src/tests/test_query_rewriter.py`:

```python
from services.query_rewriter import QueryRewriter


def test_basic_mode_returns_original_query():
    rewriter = QueryRewriter()

    queries = rewriter.rewrite(
        mode="basic",
        user_query="graph reconstruction",
        memory_context="old logs",
    )

    assert queries == ["graph reconstruction"]


def test_advanced_mode_adds_research_direction_queries():
    rewriter = QueryRewriter()

    queries = rewriter.rewrite(
        mode="advanced",
        user_query="graph reconstruction",
        memory_context="block: model is too heavy; idea: improve interpretability",
    )

    assert "graph reconstruction lightweight" in queries
    assert "graph reconstruction interpretability" in queries
```

- [ ] **Step 2: Run query rewriter test to verify failure**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_query_rewriter.py -v
```

Expected: FAIL because `services.query_rewriter` does not exist.

- [ ] **Step 3: Implement deterministic `QueryRewriter`**

Create `backend/src/services/query_rewriter.py` with:

```python
class QueryRewriter:
    def rewrite(self, mode: str, user_query: str, memory_context: str = "") -> list[str]:
        query = user_query.strip()
        if not query:
            return []
        if mode == "basic":
            return [query]

        directions = []
        context = memory_context.lower()
        if "light" in context or "heavy" in context or "轻量" in context:
            directions.append("lightweight")
        if "interpret" in context or "可解释" in context:
            directions.append("interpretability")
        if "module" in context or "模块" in context:
            directions.append("modular architecture")
        if "loss" in context or "损失" in context:
            directions.append("loss function")

        if not directions:
            directions = ["survey", "recent methods"]

        return [query] + [f"{query} {direction}" for direction in directions[:4]]
```

This is a deterministic Advanced-lite placeholder. Replace it with LLM rewriting only after the MVP is stable.

- [ ] **Step 4: Add memory context method**

Modify `backend/src/services/memory_store.py` with:

```python
def build_memory_context(self, limit: int = 20) -> str:
    logs = self.list_experiment_logs(limit=limit)
    lines = []
    for log in logs:
        tags = ",".join(log.get("tags", []))
        lines.append(f"{tags}: {log['content']}")
    return "\n".join(lines)
```

- [ ] **Step 5: Inject rewriter into graph**

Modify `backend/src/graph/builder.py` so `build_paper_discovery_graph` accepts `query_rewriter`.

Modify `backend/src/graph/nodes.py` so:

- `load_memory_context` calls `memory_store.build_memory_context()`.
- `rewrite_query` calls `query_rewriter.rewrite(...)`.

- [ ] **Step 6: Extend graph test for advanced mode**

Modify `backend/src/tests/test_paper_discovery_graph.py` by adding:

```python
from services.query_rewriter import QueryRewriter


def test_advanced_graph_uses_memory_context_for_rewritten_queries(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    store.add_experiment_log("model is too heavy", tags=["block"])

    graph = build_paper_discovery_graph(
        search_service=FakeSearchService(),
        judge=FakeJudge(),
        memory_store=store,
        query_rewriter=QueryRewriter(),
    )

    result = graph.invoke({
        "mode": "advanced",
        "user_query": "graph reconstruction",
        "memory_context": "",
        "rewritten_queries": [],
        "raw_results": [],
        "normalized_papers": [],
        "deduped_papers": [],
        "judge_results": [],
        "ranked_candidates": [],
    })

    assert "graph reconstruction lightweight" in result["rewritten_queries"]
```

- [ ] **Step 7: Run advanced-lite tests**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_query_rewriter.py backend/src/tests/test_paper_discovery_graph.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/src/services/query_rewriter.py backend/src/services/memory_store.py backend/src/graph/nodes.py backend/src/graph/builder.py backend/src/tests/test_query_rewriter.py backend/src/tests/test_paper_discovery_graph.py
git commit -m "feat: add advanced lite query rewriting"
```

---

## Task 7: Add Manual PDF Upload And Knowledge-Base Stub

**Files:**
- Modify: `pyproject.toml`
- Create: `backend/src/services/knowledge_base.py`
- Modify: `backend/src/main.py`
- Modify: `backend/src/tests/test_api_mvp.py`
- Create: `backend/src/tests/test_knowledge_base.py`

- [ ] **Step 1: Add PDF dependency**

Modify `pyproject.toml` dependencies:

```toml
"pypdf>=5.1.0",
```

- [ ] **Step 2: Write knowledge-base test**

Create `backend/src/tests/test_knowledge_base.py`:

```python
from services.knowledge_base import chunk_text


def test_chunk_text_splits_long_text_with_overlap():
    text = " ".join([f"token{i}" for i in range(120)])

    chunks = chunk_text(text, chunk_size=50, overlap=10)

    assert len(chunks) == 3
    assert chunks[0].startswith("token0")
    assert "token40" in chunks[1]
```

- [ ] **Step 3: Run knowledge-base test to verify failure**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_knowledge_base.py -v
```

Expected: FAIL because `services.knowledge_base` does not exist.

- [ ] **Step 4: Implement knowledge-base stub**

Create `backend/src/services/knowledge_base.py` with:

- `chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]`
- `KnowledgeBase.__init__(upload_dir: str, vector_store_dir: str)`
- `KnowledgeBase.save_pdf(paper_id: str, filename: str, content: bytes) -> str`
- `KnowledgeBase.ingest_pdf(paper_id: str, pdf_path: str) -> list[str]`

Implementation rules:

- `save_pdf()` writes to `<upload_dir>/<paper_id>/<filename>`.
- `ingest_pdf()` extracts text with `pypdf.PdfReader`.
- For MVP, write chunks to `<vector_store_dir>/<paper_id>.json` before wiring real embeddings.
- Return chunk ids like `paper_id:0`, `paper_id:1`.

- [ ] **Step 5: Add upload endpoint test**

Modify `backend/src/tests/test_api_mvp.py` by adding:

```python
def test_upload_pdf_marks_paper_uploaded(tmp_path):
    test_db = tmp_path / "api.sqlite3"
    app.dependency_overrides[get_memory_store] = lambda: get_memory_store(str(test_db))
    client = TestClient(app)

    store = get_memory_store(str(test_db))
    from services.schemas import PaperId, PaperMetadata
    store.save_candidate_paper(PaperMetadata(
        paper_id="p1",
        source_ids=PaperId(doi="10.1000/p1"),
        title="Upload Me",
        authors=[],
        abstract="abstract",
        doi="10.1000/p1",
        source="test",
    ))

    response = client.post(
        "/papers/p1/upload_pdf",
        files={"file": ("paper.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["paper_id"] == "p1"

    app.dependency_overrides.clear()
```

- [ ] **Step 6: Add upload endpoint**

Modify `backend/src/main.py`:

```python
from fastapi import File, UploadFile
from services.knowledge_base import KnowledgeBase


@app.post("/papers/{paper_id}/upload_pdf")
async def upload_pdf(
    paper_id: str,
    file: UploadFile = File(...),
    store: MemoryStore = Depends(get_memory_store),
):
    kb = KnowledgeBase(config.pdf_upload_dir)
    content = await file.read()
    pdf_path = kb.save_pdf(paper_id, file.filename or f"{paper_id}.pdf", content)
    text = kb.extract_text(pdf_path)
    chunks = kb.chunk_text(text)
    store.delete_knowledge_chunks_by_paper(paper_id)
    store.insert_knowledge_chunks(paper_id, chunks)
    store.update_paper_status(paper_id, "chunked", pdf_path=pdf_path)
    return {"paper_id": paper_id, "pdf_path": pdf_path, "status": "chunked", "chunk_count": len(chunks)}
```

- [ ] **Step 7: Run upload and knowledge-base tests**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests/test_knowledge_base.py backend/src/tests/test_api_mvp.py -v
```

Expected: PASS. If the minimal PDF bytes cannot be parsed, adjust `KnowledgeBase.ingest_pdf()` to return an empty chunk list on parse failure and still mark the PDF uploaded for MVP.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml backend/src/services/knowledge_base.py backend/src/main.py backend/src/tests/test_knowledge_base.py backend/src/tests/test_api_mvp.py
git commit -m "feat: add manual pdf upload"
```

---

## Task 8: Add Simple Vue Workbench

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.js`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/api.js`
- Create: `frontend/src/components/SearchWorkbench.vue`
- Create: `frontend/src/components/ExperimentLogs.vue`
- Create: `frontend/src/components/KnowledgeBase.vue`

- [ ] **Step 1: Create Vue package**

Create `frontend/package.json`:

```json
{
  "scripts": {
    "dev": "vite --host 127.0.0.1 --port 5173",
    "build": "vite build",
    "preview": "vite preview --host 127.0.0.1 --port 5173"
  },
  "dependencies": {
    "@vitejs/plugin-vue": "^5.2.0",
    "vite": "^6.0.0",
    "vue": "^3.5.0"
  },
  "devDependencies": {}
}
```

- [ ] **Step 2: Create API client**

Create `frontend/src/api.js`:

```javascript
const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

export async function searchPapers(payload) {
  const response = await fetch(`${API_BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return response.json()
}

export async function listCandidates() {
  const response = await fetch(`${API_BASE}/papers/candidates`)
  return response.json()
}

export async function addLog(payload) {
  const response = await fetch(`${API_BASE}/logs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return response.json()
}

export async function listLogs() {
  const response = await fetch(`${API_BASE}/logs`)
  return response.json()
}

export async function uploadPdf(paperId, file) {
  const data = new FormData()
  data.append('file', file)
  const response = await fetch(`${API_BASE}/papers/${paperId}/upload_pdf`, {
    method: 'POST',
    body: data,
  })
  return response.json()
}
```

- [ ] **Step 3: Create Vue shell**

Create `frontend/index.html`, `frontend/src/main.js`, and `frontend/src/App.vue` with three tabs:

```vue
<script setup>
import { ref } from 'vue'
import SearchWorkbench from './components/SearchWorkbench.vue'
import ExperimentLogs from './components/ExperimentLogs.vue'
import KnowledgeBase from './components/KnowledgeBase.vue'

const active = ref('search')
</script>

<template>
  <main class="app">
    <nav class="tabs">
      <button @click="active = 'search'">检索</button>
      <button @click="active = 'logs'">日志</button>
      <button @click="active = 'kb'">知识库</button>
    </nav>
    <SearchWorkbench v-if="active === 'search'" />
    <ExperimentLogs v-if="active === 'logs'" />
    <KnowledgeBase v-if="active === 'kb'" />
  </main>
</template>
```

- [ ] **Step 4: Implement search component**

Create `frontend/src/components/SearchWorkbench.vue` with:

- Basic / Advanced-lite mode selector.
- Query input.
- Search button.
- Candidate table.
- PDF upload input per candidate.

Use the functions from `frontend/src/api.js`.

- [ ] **Step 5: Implement logs component**

Create `frontend/src/components/ExperimentLogs.vue` with:

- Textarea for log content.
- Comma-separated tags input.
- Save button.
- Recent logs list.

- [ ] **Step 6: Implement knowledge-base component**

Create `frontend/src/components/KnowledgeBase.vue` with:

- Candidate/known paper list from `listCandidates()`.
- Show title, DOI, status, and PDF path if present.

- [ ] **Step 7: Build frontend**

Run:

```bash
cd frontend
npm install
npm run build
```

Expected: Vite build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/index.html frontend/src
git commit -m "feat: add vue research workbench"
```

---

## Task 9: MVP End-To-End Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run backend tests**

Run:

```bash
PYTHONPATH=backend/src pytest backend/src/tests -v
```

Expected: all MVP tests pass.

- [ ] **Step 2: Start backend**

Run:

```bash
PYTHONPATH=backend/src uvicorn main:app --app-dir backend/src --port 8000
```

Expected: FastAPI app starts on `http://127.0.0.1:8000`.

- [ ] **Step 3: Smoke test logs**

Run:

```bash
curl -s -X POST http://127.0.0.1:8000/logs \
  -H 'Content-Type: application/json' \
  -d '{"content":"baseline experiment failed because memory usage is high","tags":["block"]}'
```

Expected: JSON with an `id`.

- [ ] **Step 4: Smoke test search**

Run:

```bash
curl -s -X POST http://127.0.0.1:8000/search \
  -H 'Content-Type: application/json' \
  -d '{"mode":"basic","query":"graph neural network reconstruction"}'
```

Expected: JSON list of ranked candidates. If external network is unavailable, record that API structure works and keep live source verification for a network-enabled run.

- [ ] **Step 5: Start frontend**

Run:

```bash
cd frontend
npm run dev
```

Expected: Vue app starts on `http://127.0.0.1:5173`.

- [ ] **Step 6: Manual browser check**

Open `http://127.0.0.1:5173` and verify:

- Search page renders.
- Logs page saves and lists logs.
- Knowledge-base page renders paper rows.
- PDF upload button calls the backend endpoint.

- [ ] **Step 7: Update README**

Modify `README.md` with:

````markdown
# Research Management MVP

## Backend

```bash
PYTHONPATH=backend/src uvicorn main:app --app-dir backend/src --port 8000
```

## Tests

```bash
PYTHONPATH=backend/src pytest backend/src/tests -v
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

## MVP Scope

- Basic paper search and ranking
- Advanced-lite query rewriting from experiment logs
- SQLite persistence for logs, candidates, judgements, and uploaded papers
- Manual PDF upload
- Local knowledge-base chunk storage

SSE and full async workflows are planned after the MVP.
````

- [ ] **Step 8: Commit**

```bash
git add README.md
git commit -m "docs: add mvp run instructions"
```

---

## Implementation Notes

- Use `PYTHONPATH=backend/src` for backend tests until the package layout is formalized.
- Keep `LLMJudge` as mock scoring in the MVP. Replace with real LLM calls only after API, graph, and persistence are stable.
- Keep `QueryRewriter` deterministic in the MVP. It provides the Advanced-lite interface without introducing LLM reliability issues too early.
- Do not register DOI values during candidate discovery. Only `uploaded`, `chunked`, and `embedded` papers participate in hard DOI deduplication.
- Treat network-backed arXiv/OpenAlex tests as smoke tests, not unit tests. Use fake adapters for deterministic automated tests.
- Avoid SSE until the REST flow is stable end to end.

## Self-Review

Spec coverage:

- Basic search flow is covered by Tasks 1, 3, 4, and 5.
- Advanced-lite query rewriting is covered by Task 6.
- SQLite persistence is covered by Task 2.
- DOI dedup based on uploaded/chunked/embedded papers is covered by Task 3.
- PDF upload and local chunk storage are covered by Task 7.
- Vue workbench is covered by Task 8.
- MVP verification and README instructions are covered by Task 9.
- SSE is intentionally excluded and documented as post-MVP.

Placeholder scan:

- No task depends on unspecified SSE behavior.
- Real LLM calls are intentionally avoided for MVP reliability.
- Real vector embeddings are intentionally deferred behind a local chunk-storage interface.

Type consistency:

- `PaperDiscoveryState`, `RankedCandidate`, `PaperMetadata`, and `JudgeResult` are used consistently across graph tests, graph nodes, and API responses.
- `MemoryStore.list_known_dois()` is the single source for hard DOI deduplication.
- `mode` uses lowercase `basic` and `advanced` across API schemas, graph state, and query rewriting.
