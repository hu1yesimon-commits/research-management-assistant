# Agent Workflow Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backend-only `POST /research/assistant` LangGraph thin orchestration entrypoint that routes between basic exploration, advanced search, advanced-ready next action, and research idea generation while reusing the existing discovery, knowledge, memory, and idea services.

**Architecture:** Add a small assistant graph layer around existing services. The new graph owns request state, deterministic coverage scoring, route selection, assistant-facing response fields, and partial-error collection; coarse-grained nodes delegate to `paper_discovery_graph`, `KnowledgeQAService`, `IdeaRecommendationService`, and `MemoryStore.build_memory_context()`. Keep `/research/query` unchanged and do not modify the frontend.

**Tech Stack:** FastAPI, Pydantic, LangGraph `StateGraph`, SQLite-backed `MemoryStore`, existing fake/deterministic providers, pytest.

---

## Planning Decisions

### Deterministic overlap tokenizer / normalize rules

The tokenizer and normalize rules constrain how the first-version `coverage_score` decides whether a query belongs to an explored area. They are not NLP quality work; they are a deterministic contract so the same query and memory produce the same route in tests and demos.

Use this first-version rule:

- Lowercase text.
- Extract ASCII alphanumeric tokens with `re.findall(r"[a-z0-9]+", text.lower())`.
- Drop a small stopword set: `a`, `an`, `and`, `are`, `as`, `for`, `from`, `how`, `i`, `in`, `is`, `it`, `of`, `on`, `or`, `should`, `the`, `to`, `with`.
- Drop tokens shorter than 2 characters.
- Compute overlap as `len(query_tokens & context_tokens) / len(query_tokens)`.
- Clamp score to `[0.0, 1.0]`.

This makes casing, punctuation, hyphens, and common English words irrelevant, while keeping the coverage heuristic explainable.

### `advanced_search` discovery/knowledge behavior

`advanced_search` should follow `/research/query` semantics:

- Run the existing discovery graph and slice to `top_k`.
- Run `KnowledgeQAService.answer(query, top_k=top_k)`.
- Preserve partial success if one section fails and the other succeeds.
- Keep discovery candidates separate from knowledge sources.

The assistant graph adds route/context/message fields around this behavior; it does not change discovery or knowledge contracts.

### Response schema recommendation

Use a new assistant envelope and reuse existing section schemas:

- New: `ResearchAssistantRequest`
- New: `ResearchAssistantNextAction`
- New: `ResearchAssistantError`
- New: `ResearchAssistantResponse`
- Reuse: `ResearchDiscoverySection`
- Reuse: `ResearchKnowledgeSection`
- Reuse: `IdeaOption`
- Reuse: `ExperimentLogRequest`

This keeps response sections consistent with current `/research/query` and `/ideas/recommend`, while giving the future frontend a conversation-oriented wrapper.

---

## File Structure

- Create: `backend/src/services/coverage.py`
  - Owns deterministic token normalization, overlap scoring, and coverage scoring.
- Create: `backend/src/graph/assistant_state.py`
  - Defines `ResearchAssistantState` and route/mode/intent literals.
- Create: `backend/src/graph/assistant_nodes.py`
  - Defines coarse-grained LangGraph node factories for memory loading, coverage assessment, routing, route execution, and response formatting.
- Modify: `backend/src/graph/builder.py`
  - Adds `build_research_assistant_graph` without changing `build_paper_discovery_graph`.
- Create: `backend/src/services/research_assistant_workflow.py`
  - Wraps the assistant graph behind a service-friendly API for FastAPI dependency injection and tests.
- Modify: `backend/src/services/schemas.py`
  - Adds assistant request/response envelope schemas.
- Modify: `backend/src/main.py`
  - Adds dependency builder and `POST /research/assistant`.
- Create: `backend/src/tests/test_coverage.py`
  - Focused tests for deterministic overlap and coverage scoring.
- Create: `backend/src/tests/test_research_assistant_workflow.py`
  - Service/graph-level route tests with fake dependencies.
- Modify: `backend/src/tests/test_api_mvp.py`
  - Adds API smoke tests for `/research/assistant`.
- Modify after implementation: `README.md` and `docs/interview/demo-script.md`
  - Only after tests pass, update docs to state implemented behavior. Preserve existing user edits.

---

### Task 1: Assistant Schemas

**Files:**
- Modify: `backend/src/services/schemas.py`
- Test indirectly in later tasks through service and API response validation.

- [ ] **Step 1: Add assistant schema imports if needed**

Ensure the top of `backend/src/services/schemas.py` keeps this import shape:

```python
from enum import Enum
from pydantic import BaseModel, Field
from typing import Literal
```

- [ ] **Step 2: Add assistant request/response schemas after `ResearchQueryResponse`**

Add this block after `ResearchQueryResponse`:

```python
class ResearchAssistantNextAction(BaseModel):
    type: Literal["choose_intent", "upload_pdf", "select_idea", "none"]
    options: list[str] = Field(default_factory=list)
    message: str | None = None


class ResearchAssistantError(BaseModel):
    section: Literal["coverage", "discovery", "knowledge", "idea", "routing"]
    message: str


class ResearchAssistantRequest(BaseModel):
    query: str
    intent: Literal["auto", "search", "research"] = "auto"
    experiment_log: ExperimentLogRequest | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    idea_count: int = Field(default=3, ge=3, le=5)
    save_log: bool = True
    include_discovery: bool = False


class ResearchAssistantResponse(BaseModel):
    query: str
    intent: Literal["auto", "search", "research"]
    mode: Literal["basic", "advanced"]
    route: Literal["basic_explore", "advanced_ready", "advanced_search", "research_idea"]
    coverage_score: float = Field(ge=0, le=1)
    route_reason: str
    assistant_message: str
    next_action: ResearchAssistantNextAction | None = None
    suggested_user_actions: list[str] = Field(default_factory=list)
    discovery: ResearchDiscoverySection
    knowledge: ResearchKnowledgeSection
    ideas: list[IdeaOption] = Field(default_factory=list)
    errors: list[ResearchAssistantError] = Field(default_factory=list)
```

- [ ] **Step 3: Run a schema import check**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python - <<'PY'
from services.schemas import ResearchAssistantRequest, ResearchAssistantResponse
print(ResearchAssistantRequest(query="graph").model_dump()["intent"])
print(ResearchAssistantResponse)
PY
```

Expected:

```text
auto
<class 'services.schemas.ResearchAssistantResponse'>
```

- [ ] **Step 4: Commit**

```bash
git add backend/src/services/schemas.py
git commit -m "feat: add research assistant schemas"
```

---

### Task 2: Deterministic Coverage Helper

**Files:**
- Create: `backend/src/services/coverage.py`
- Create: `backend/src/tests/test_coverage.py`

- [ ] **Step 1: Write failing tests**

Create `backend/src/tests/test_coverage.py`:

```python
from services.coverage import calculate_coverage_score, normalize_tokens, overlap_score


def test_normalize_tokens_lowercases_splits_and_removes_stopwords():
    assert normalize_tokens("How should I improve Graph-Reconstruction, with GNN?") == {
        "improve",
        "graph",
        "reconstruction",
        "gnn",
    }


def test_overlap_score_uses_query_token_denominator():
    score = overlap_score("graph reconstruction precision", "confirmed graph reconstruction memory")

    assert score == 2 / 3


def test_calculate_coverage_score_combines_memory_logs_and_knowledge_signal():
    score, reason = calculate_coverage_score(
        query="graph reconstruction precision",
        semantic_memory_text="User focuses on graph reconstruction.",
        recent_log_text="Recent episodic memory mentions precision collapse.",
        has_knowledge_sources=True,
    )

    assert round(score, 2) == 0.67
    assert "semantic=0.67" in reason
    assert "recent_logs=0.33" in reason
    assert "knowledge=1.00" in reason


def test_calculate_coverage_score_returns_zero_for_empty_signals():
    score, reason = calculate_coverage_score(
        query="unknown topic",
        semantic_memory_text="",
        recent_log_text="",
        has_knowledge_sources=False,
    )

    assert score == 0.0
    assert "knowledge=0.00" in reason
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_coverage.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'services.coverage'`.

- [ ] **Step 3: Implement coverage helper**

Create `backend/src/services/coverage.py`:

```python
from __future__ import annotations

import re


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "should",
    "the",
    "to",
    "with",
}


def normalize_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {token for token in tokens if len(token) >= 2 and token not in STOPWORDS}


def overlap_score(query: str, context: str) -> float:
    query_tokens = normalize_tokens(query)
    if not query_tokens:
        return 0.0
    context_tokens = normalize_tokens(context)
    score = len(query_tokens & context_tokens) / len(query_tokens)
    return _clamp(score)


def calculate_coverage_score(
    query: str,
    semantic_memory_text: str,
    recent_log_text: str,
    has_knowledge_sources: bool,
) -> tuple[float, str]:
    semantic_score = overlap_score(query, semantic_memory_text)
    recent_log_score = overlap_score(query, recent_log_text)
    knowledge_score = 1.0 if has_knowledge_sources else 0.0
    score = _clamp(
        (0.4 * semantic_score)
        + (0.3 * recent_log_score)
        + (0.3 * knowledge_score)
    )
    reason = (
        f"coverage heuristic: semantic={semantic_score:.2f}, "
        f"recent_logs={recent_log_score:.2f}, "
        f"knowledge={knowledge_score:.2f}"
    )
    return score, reason


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
```

- [ ] **Step 4: Run coverage tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_coverage.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/coverage.py backend/src/tests/test_coverage.py
git commit -m "feat: add deterministic assistant coverage scoring"
```

---

### Task 3: Assistant State And Graph Nodes

**Files:**
- Create: `backend/src/graph/assistant_state.py`
- Create: `backend/src/graph/assistant_nodes.py`
- Modify: `backend/src/graph/builder.py`
- Create: `backend/src/tests/test_research_assistant_workflow.py`

- [ ] **Step 1: Write failing workflow route tests**

Create `backend/src/tests/test_research_assistant_workflow.py`:

```python
from services.qa_service import QAServiceError
from services.research_assistant_workflow import ResearchAssistantWorkflowError, ResearchAssistantWorkflowService
from services.schemas import (
    ExperimentLogRequest,
    IdeaDiscoverySection,
    IdeaKnowledgeSection,
    IdeaRecommendResponse,
    IdeaOption,
    KnowledgeAnswerResponse,
    KnowledgeAnswerSource,
)


class FakeStore:
    def __init__(self, memory_context: str = ""):
        self.memory_context = memory_context

    def build_memory_context(self) -> str:
        return self.memory_context


class FakeDiscoveryGraph:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result if result is not None else [{"paper": {"paper_id": "d1", "title": "Discovery Paper"}}]
        self.error = error
        self.calls: list[dict] = []

    def invoke(self, state: dict) -> dict:
        self.calls.append(state)
        if self.error is not None:
            raise self.error
        return {**state, "ranked_candidates": self.result}


class FakeKnowledgeQAService:
    def __init__(self, response: KnowledgeAnswerResponse | None = None, error: Exception | None = None):
        self.response = response or KnowledgeAnswerResponse(
            question="graph reconstruction",
            answer="Knowledge answer",
            sources=[
                KnowledgeAnswerSource(
                    paper_id="k1",
                    title="Knowledge Paper",
                    chunk_index=0,
                    distance=0.1,
                    text="embedded graph reconstruction chunk",
                    vector_ref="chroma:research_chunks:k1:0:hash",
                )
            ],
            mode="deterministic",
        )
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def answer(self, question: str, top_k: int = 5) -> KnowledgeAnswerResponse:
        self.calls.append((question, top_k))
        if self.error is not None:
            raise self.error
        return self.response


class FakeIdeaService:
    def __init__(self):
        self.calls = []

    def recommend(
        self,
        experiment_log: ExperimentLogRequest,
        save_log: bool = True,
        include_discovery: bool = False,
        top_k: int = 5,
        idea_count: int = 3,
    ) -> IdeaRecommendResponse:
        self.calls.append((experiment_log, save_log, include_discovery, top_k, idea_count))
        return IdeaRecommendResponse(
            log_id=1 if save_log else None,
            query=" ".join([experiment_log.task, experiment_log.goal]),
            knowledge=IdeaKnowledgeSection(sources=[]),
            discovery=IdeaDiscoverySection(enabled=include_discovery, candidates=[]),
            ideas=[
                IdeaOption(
                    title="Try calibrated retrieval",
                    rationale="Use the experiment log and memory context.",
                    supporting_evidence=[],
                    expected_benefit="Improve precision.",
                    risk="May overfit validation data.",
                    suggested_validation_metric="PRAUC",
                    next_small_experiment="Run one calibration sweep.",
                )
            ],
            mode="deterministic",
        )


def make_log() -> ExperimentLogRequest:
    return ExperimentLogRequest(
        task="graph reconstruction",
        model="GCN",
        dataset="citation graph",
        metric_problem="precision is low",
        tried_methods=["focal loss"],
        observation="recall improves but precision drops",
        goal="improve graph reconstruction precision",
        tags=["graph"],
    )


def build_service(
    store: FakeStore | None = None,
    discovery_graph: FakeDiscoveryGraph | None = None,
    knowledge_service: FakeKnowledgeQAService | None = None,
    idea_service: FakeIdeaService | None = None,
) -> ResearchAssistantWorkflowService:
    return ResearchAssistantWorkflowService(
        store=store or FakeStore(),
        discovery_graph=discovery_graph or FakeDiscoveryGraph(),
        knowledge_qa_service=knowledge_service or FakeKnowledgeQAService(),
        idea_service=idea_service or FakeIdeaService(),
    )


def test_auto_low_coverage_routes_to_basic_explore():
    knowledge = FakeKnowledgeQAService(
        response=KnowledgeAnswerResponse(
            question="new topic",
            answer="No relevant knowledge chunks were found.",
            sources=[],
            mode="deterministic",
        )
    )
    service = build_service(store=FakeStore("Confirmed semantic memory:\nRecent episodic memory:"), knowledge_service=knowledge)

    response = service.query(query="brand new topic", intent="auto", top_k=3)

    assert response.mode == "basic"
    assert response.route == "basic_explore"
    assert response.discovery.candidates[0]["paper"]["paper_id"] == "d1"
    assert response.knowledge.answer == "No relevant knowledge chunks were found."
    assert response.next_action is not None
    assert response.next_action.type == "upload_pdf"


def test_auto_high_coverage_routes_to_advanced_ready_without_running_discovery():
    discovery = FakeDiscoveryGraph()
    knowledge = FakeKnowledgeQAService()
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        discovery_graph=discovery,
        knowledge_service=knowledge,
    )

    response = service.query(query="graph reconstruction precision", intent="auto", top_k=5)

    assert response.mode == "advanced"
    assert response.route == "advanced_ready"
    assert response.discovery.enabled is False
    assert response.knowledge.enabled is False
    assert discovery.calls == []
    assert knowledge.calls == [("graph reconstruction precision", 5)]
    assert response.next_action is not None
    assert response.next_action.type == "choose_intent"


def test_search_intent_routes_to_advanced_search_and_preserves_partial_discovery_failure():
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        discovery_graph=FakeDiscoveryGraph(error=RuntimeError("discovery offline")),
        knowledge_service=FakeKnowledgeQAService(),
    )

    response = service.query(query="graph reconstruction precision", intent="search", top_k=5)

    assert response.mode == "advanced"
    assert response.route == "advanced_search"
    assert response.discovery.error == "discovery offline"
    assert response.knowledge.answer == "Knowledge answer"
    assert response.errors[0].section == "discovery"


def test_research_intent_requires_experiment_log():
    service = build_service()

    try:
        service.query(query="graph reconstruction", intent="research", experiment_log=None)
    except ResearchAssistantWorkflowError as exc:
        assert exc.status_code == 400
        assert "experiment_log is required" in exc.detail
    else:
        raise AssertionError("expected ResearchAssistantWorkflowError")


def test_research_intent_routes_to_idea_service():
    idea_service = FakeIdeaService()
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        idea_service=idea_service,
    )

    response = service.query(query="graph reconstruction precision", intent="research", experiment_log=make_log())

    assert response.mode == "advanced"
    assert response.route == "research_idea"
    assert response.ideas[0].title == "Try calibrated retrieval"
    assert len(idea_service.calls) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'services.research_assistant_workflow'`.

- [ ] **Step 3: Add assistant state**

Create `backend/src/graph/assistant_state.py`:

```python
from typing import Literal, TypedDict

from services.schemas import ExperimentLogRequest


AssistantIntent = Literal["auto", "search", "research"]
AssistantMode = Literal["basic", "advanced"]
AssistantRoute = Literal["basic_explore", "advanced_ready", "advanced_search", "research_idea"]


class ResearchAssistantState(TypedDict):
    query: str
    intent: AssistantIntent
    experiment_log: ExperimentLogRequest | None
    top_k: int
    idea_count: int
    save_log: bool
    include_discovery: bool
    memory_context: str
    coverage_score: float
    mode: AssistantMode
    route: AssistantRoute
    route_reason: str
    discovery: dict
    knowledge: dict
    ideas: list[dict]
    assistant_message: str
    next_action: dict | None
    suggested_user_actions: list[str]
    errors: list[dict]
```

- [ ] **Step 4: Add assistant graph nodes**

Create `backend/src/graph/assistant_nodes.py`:

```python
from __future__ import annotations

from services.coverage import calculate_coverage_score
from services.idea_service import IdeaServiceError
from services.qa_service import QAServiceError
from services.schemas import ResearchDiscoverySection, ResearchKnowledgeSection


ADVANCED_THRESHOLD = 0.5


def make_research_assistant_nodes(
    store,
    discovery_graph,
    knowledge_qa_service,
    idea_service,
):
    def load_memory_context(state: dict) -> dict:
        return {"memory_context": store.build_memory_context()}

    def assess_query_coverage(state: dict) -> dict:
        knowledge_response = None
        has_sources = False
        try:
            knowledge_response = knowledge_qa_service.answer(state["query"], top_k=state["top_k"])
            has_sources = bool(knowledge_response.sources)
        except QAServiceError:
            has_sources = False
        score, reason = calculate_coverage_score(
            query=state["query"],
            semantic_memory_text=_semantic_memory_text(state["memory_context"]),
            recent_log_text=_recent_log_text(state["memory_context"]),
            has_knowledge_sources=has_sources,
        )
        updates = {
            "coverage_score": score,
            "route_reason": reason,
        }
        if knowledge_response is not None:
            updates["knowledge"] = _knowledge_section(enabled=False, response=knowledge_response).model_dump()
        return updates

    def route_request(state: dict) -> dict:
        intent = state["intent"]
        if intent == "research":
            return {"mode": "advanced", "route": "research_idea"}
        if intent == "search":
            return {"mode": "advanced", "route": "advanced_search"}
        if state["coverage_score"] >= ADVANCED_THRESHOLD:
            return {"mode": "advanced", "route": "advanced_ready"}
        return {"mode": "basic", "route": "basic_explore"}

    def run_basic_explore(state: dict) -> dict:
        discovery, errors = _run_discovery(discovery_graph, state, enabled=True)
        knowledge, knowledge_errors = _run_knowledge(knowledge_qa_service, state, enabled=True)
        errors.extend(knowledge_errors)
        return {
            "discovery": discovery.model_dump(),
            "knowledge": knowledge.model_dump(),
            "assistant_message": (
                "This looks like a new or lightly covered research area. I recommended top papers "
                "and checked the local knowledge base. Select useful candidates and upload PDFs to "
                "improve later research assistance."
            ),
            "next_action": {
                "type": "upload_pdf",
                "options": ["review_candidates", "upload_pdf"],
                "message": "Review the recommended papers and upload PDFs for the ones you want to keep.",
            },
            "suggested_user_actions": [
                "Review the recommended discovery candidates.",
                "Accept useful papers and upload PDFs.",
                "Run embedding after upload so future answers can cite local chunks.",
            ],
            "errors": state["errors"] + errors,
        }

    def run_advanced_ready(state: dict) -> dict:
        return {
            "discovery": ResearchDiscoverySection(enabled=False).model_dump(),
            "knowledge": ResearchKnowledgeSection(enabled=False).model_dump(),
            "assistant_message": (
                "This query appears related to your existing research context. Do you have a new "
                "experiment log to analyze, or should I continue with contextual search?"
            ),
            "next_action": {
                "type": "choose_intent",
                "options": ["research", "search"],
                "message": "Choose research if you have a structured experiment log; choose search for contextual papers and answers.",
            },
            "suggested_user_actions": [
                "Submit a structured experiment log for idea recommendations.",
                "Continue with search for contextual paper recommendations and knowledge-base answers.",
            ],
        }

    def run_advanced_search(state: dict) -> dict:
        discovery, errors = _run_discovery(discovery_graph, state, enabled=True)
        knowledge, knowledge_errors = _run_knowledge(knowledge_qa_service, state, enabled=True)
        errors.extend(knowledge_errors)
        return {
            "discovery": discovery.model_dump(),
            "knowledge": knowledge.model_dump(),
            "assistant_message": (
                "I used your existing research context to run contextual discovery and local knowledge answering."
            ),
            "next_action": {
                "type": "none",
                "options": [],
                "message": "You can accept papers, upload PDFs, or submit an experiment log next.",
            },
            "suggested_user_actions": [
                "Review contextual discovery candidates.",
                "Use knowledge sources as grounded evidence.",
                "Submit an experiment log if you want idea recommendations.",
            ],
            "errors": state["errors"] + errors,
        }

    def run_research_idea(state: dict) -> dict:
        experiment_log = state["experiment_log"]
        if experiment_log is None:
            return {
                "errors": state["errors"] + [{"section": "idea", "message": "experiment_log is required for research intent"}]
            }
        try:
            response = idea_service.recommend(
                experiment_log=experiment_log,
                save_log=state["save_log"],
                include_discovery=state["include_discovery"],
                top_k=state["top_k"],
                idea_count=state["idea_count"],
            )
        except IdeaServiceError as exc:
            return {
                "ideas": [],
                "assistant_message": "I could not generate idea recommendations from this experiment log.",
                "errors": state["errors"] + [{"section": "idea", "message": exc.detail}],
            }
        return {
            "discovery": ResearchDiscoverySection(
                enabled=response.discovery.enabled,
                candidates=response.discovery.candidates,
                error=response.discovery.error,
            ).model_dump(),
            "knowledge": ResearchKnowledgeSection(
                enabled=True,
                answer=None,
                sources=response.knowledge.sources,
                error=response.knowledge.error,
                mode=response.mode,
            ).model_dump(),
            "ideas": [idea.model_dump() for idea in response.ideas],
            "assistant_message": "I generated idea options from your experiment log, memory context, and available evidence.",
            "next_action": {
                "type": "select_idea",
                "options": ["select_idea", "continue_search"],
                "message": "Choose one idea to explore further, or continue with contextual search.",
            },
            "suggested_user_actions": [
                "Pick one idea for a small validation experiment.",
                "Use supporting evidence to decide which idea is safest.",
                "Continue with search if you want more papers around a selected idea.",
            ],
        }

    def format_assistant_response(state: dict) -> dict:
        return state

    return {
        "load_memory_context": load_memory_context,
        "assess_query_coverage": assess_query_coverage,
        "route_request": route_request,
        "run_basic_explore": run_basic_explore,
        "run_advanced_ready": run_advanced_ready,
        "run_advanced_search": run_advanced_search,
        "run_research_idea": run_research_idea,
        "format_assistant_response": format_assistant_response,
    }


def route_by_state(state: dict) -> str:
    return state["route"]


def _run_discovery(discovery_graph, state: dict, enabled: bool) -> tuple[ResearchDiscoverySection, list[dict]]:
    if not enabled:
        return ResearchDiscoverySection(enabled=False), []
    try:
        result = discovery_graph.invoke(
            {
                "mode": state["mode"],
                "user_query": state["query"],
                "memory_context": "",
                "rewritten_queries": [],
                "raw_results": [],
                "normalized_papers": [],
                "deduped_papers": [],
                "judge_results": [],
                "ranked_candidates": [],
            }
        )
        return ResearchDiscoverySection(
            enabled=True,
            candidates=result["ranked_candidates"][: state["top_k"]],
            error=None,
        ), []
    except Exception as exc:
        message = str(exc)
        return ResearchDiscoverySection(enabled=True, candidates=[], error=message), [
            {"section": "discovery", "message": message}
        ]


def _run_knowledge(knowledge_qa_service, state: dict, enabled: bool) -> tuple[ResearchKnowledgeSection, list[dict]]:
    if not enabled:
        return ResearchKnowledgeSection(enabled=False), []
    try:
        response = knowledge_qa_service.answer(state["query"], top_k=state["top_k"])
        return _knowledge_section(enabled=True, response=response), []
    except QAServiceError as exc:
        return ResearchKnowledgeSection(enabled=True, answer=None, sources=[], error=exc.detail, mode=None), [
            {"section": "knowledge", "message": exc.detail}
        ]


def _knowledge_section(enabled: bool, response) -> ResearchKnowledgeSection:
    return ResearchKnowledgeSection(
        enabled=enabled,
        answer=response.answer,
        sources=response.sources,
        error=None,
        mode=response.mode,
    )


def _semantic_memory_text(memory_context: str) -> str:
    return memory_context.split("Recent episodic memory:", 1)[0]


def _recent_log_text(memory_context: str) -> str:
    if "Recent episodic memory:" not in memory_context:
        return ""
    return memory_context.split("Recent episodic memory:", 1)[1]
```

- [ ] **Step 5: Add assistant graph builder**

Modify `backend/src/graph/builder.py` to import assistant helpers:

```python
from graph.assistant_nodes import make_research_assistant_nodes, route_by_state
from graph.assistant_state import ResearchAssistantState
```

Then add this function at the bottom:

```python
def build_research_assistant_graph(
    store,
    discovery_graph,
    knowledge_qa_service,
    idea_service,
):
    nodes = make_research_assistant_nodes(
        store=store,
        discovery_graph=discovery_graph,
        knowledge_qa_service=knowledge_qa_service,
        idea_service=idea_service,
    )

    builder = StateGraph(ResearchAssistantState)
    for name, node in nodes.items():
        builder.add_node(name, node)

    builder.add_edge(START, "load_memory_context")
    builder.add_edge("load_memory_context", "assess_query_coverage")
    builder.add_edge("assess_query_coverage", "route_request")
    builder.add_conditional_edges(
        "route_request",
        route_by_state,
        {
            "basic_explore": "run_basic_explore",
            "advanced_ready": "run_advanced_ready",
            "advanced_search": "run_advanced_search",
            "research_idea": "run_research_idea",
        },
    )
    builder.add_edge("run_basic_explore", "format_assistant_response")
    builder.add_edge("run_advanced_ready", "format_assistant_response")
    builder.add_edge("run_advanced_search", "format_assistant_response")
    builder.add_edge("run_research_idea", "format_assistant_response")
    builder.add_edge("format_assistant_response", END)

    return builder.compile()
```

- [ ] **Step 6: Add workflow service**

Create `backend/src/services/research_assistant_workflow.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from graph.builder import build_research_assistant_graph
from services.schemas import (
    ExperimentLogRequest,
    ResearchAssistantError,
    ResearchAssistantNextAction,
    ResearchAssistantResponse,
    ResearchDiscoverySection,
    ResearchKnowledgeSection,
)


class ResearchAssistantWorkflowError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass
class ResearchAssistantWorkflowService:
    store: object
    discovery_graph: object
    knowledge_qa_service: object
    idea_service: object

    def query(
        self,
        query: str,
        intent: str = "auto",
        experiment_log: ExperimentLogRequest | None = None,
        top_k: int = 5,
        idea_count: int = 3,
        save_log: bool = True,
        include_discovery: bool = False,
    ) -> ResearchAssistantResponse:
        normalized_query = query.strip()
        if not normalized_query:
            raise ResearchAssistantWorkflowError("query must not be empty", status_code=400)
        if intent == "research" and experiment_log is None:
            raise ResearchAssistantWorkflowError("experiment_log is required for research intent", status_code=400)

        graph = build_research_assistant_graph(
            store=self.store,
            discovery_graph=self.discovery_graph,
            knowledge_qa_service=self.knowledge_qa_service,
            idea_service=self.idea_service,
        )
        result = graph.invoke(
            {
                "query": normalized_query,
                "intent": intent,
                "experiment_log": experiment_log,
                "top_k": top_k,
                "idea_count": idea_count,
                "save_log": save_log,
                "include_discovery": include_discovery,
                "memory_context": "",
                "coverage_score": 0.0,
                "mode": "basic",
                "route": "basic_explore",
                "route_reason": "",
                "discovery": ResearchDiscoverySection(enabled=False).model_dump(),
                "knowledge": ResearchKnowledgeSection(enabled=False).model_dump(),
                "ideas": [],
                "assistant_message": "",
                "next_action": None,
                "suggested_user_actions": [],
                "errors": [],
            }
        )

        return ResearchAssistantResponse(
            query=result["query"],
            intent=result["intent"],
            mode=result["mode"],
            route=result["route"],
            coverage_score=result["coverage_score"],
            route_reason=result["route_reason"],
            assistant_message=result["assistant_message"],
            next_action=(
                ResearchAssistantNextAction(**result["next_action"])
                if result.get("next_action") is not None
                else None
            ),
            suggested_user_actions=result["suggested_user_actions"],
            discovery=ResearchDiscoverySection(**result["discovery"]),
            knowledge=ResearchKnowledgeSection(**result["knowledge"]),
            ideas=result["ideas"],
            errors=[ResearchAssistantError(**error) for error in result["errors"]],
        )
```

- [ ] **Step 7: Run workflow tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/src/graph/assistant_state.py backend/src/graph/assistant_nodes.py backend/src/graph/builder.py backend/src/services/research_assistant_workflow.py backend/src/tests/test_research_assistant_workflow.py
git commit -m "feat: add research assistant workflow graph"
```

---

### Task 4: FastAPI Endpoint

**Files:**
- Modify: `backend/src/main.py`
- Modify: `backend/src/tests/test_api_mvp.py`

- [ ] **Step 1: Add failing API tests**

Append these tests near the existing `/research/query` tests in `backend/src/tests/test_api_mvp.py`:

```python
def test_research_assistant_basic_explore_response(tmp_path):
    test_db = tmp_path / "api-research-assistant.sqlite3"
    store = get_memory_store(str(test_db))
    workflow = ResearchAssistantWorkflowService(
        store=store,
        discovery_graph=FakeGraph(store),
        knowledge_qa_service=FakeKnowledgeQAService(
            response=KnowledgeAnswerResponse(
                question="brand new topic",
                answer="No relevant knowledge chunks were found.",
                sources=[],
                mode="deterministic",
            )
        ),
        idea_service=object(),
    )

    app.dependency_overrides[get_research_assistant_workflow_service] = lambda: workflow
    client = TestClient(app)

    response = client.post("/research/assistant", json={"query": "brand new topic", "top_k": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "basic_explore"
    assert body["mode"] == "basic"
    assert body["discovery"]["enabled"] is True
    assert body["knowledge"]["answer"] == "No relevant knowledge chunks were found."
    assert body["next_action"]["type"] == "upload_pdf"

    app.dependency_overrides.clear()


def test_research_assistant_rejects_blank_query(tmp_path):
    test_db = tmp_path / "api-research-assistant-blank.sqlite3"
    store = get_memory_store(str(test_db))
    workflow = ResearchAssistantWorkflowService(
        store=store,
        discovery_graph=FakeGraph(store),
        knowledge_qa_service=FakeKnowledgeQAService(),
        idea_service=object(),
    )

    app.dependency_overrides[get_research_assistant_workflow_service] = lambda: workflow
    client = TestClient(app)

    response = client.post("/research/assistant", json={"query": "   "})

    assert response.status_code == 400

    app.dependency_overrides.clear()
```

Also add imports near the top of the file:

```python
from services.research_assistant_workflow import ResearchAssistantWorkflowService
from main import get_research_assistant_workflow_service
```

If `main` imports are already grouped, extend the existing import rather than adding a duplicate.

- [ ] **Step 2: Run API tests to verify they fail**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_api_mvp.py::test_research_assistant_basic_explore_response backend/src/tests/test_api_mvp.py::test_research_assistant_rejects_blank_query -q
```

Expected: FAIL because `get_research_assistant_workflow_service` or `/research/assistant` is not defined.

- [ ] **Step 3: Wire imports in `main.py`**

Modify `backend/src/main.py` imports:

```python
from services.research_assistant_workflow import ResearchAssistantWorkflowError, ResearchAssistantWorkflowService
```

Add these schema imports in the existing multi-line `from services.schemas import` block:

```python
    ResearchAssistantRequest,
    ResearchAssistantResponse,
```

- [ ] **Step 4: Add dependency builder**

Add after `get_research_workflow_service`:

```python
def get_research_assistant_workflow_service(
    store: MemoryStore = Depends(get_memory_store),
    discovery_graph=Depends(get_paper_discovery_graph),
    qa_service: KnowledgeQAService = Depends(get_knowledge_qa_service),
    idea_service: IdeaRecommendationService = Depends(get_idea_recommendation_service),
) -> ResearchAssistantWorkflowService:
    return ResearchAssistantWorkflowService(
        store=store,
        discovery_graph=discovery_graph,
        knowledge_qa_service=qa_service,
        idea_service=idea_service,
    )
```

- [ ] **Step 5: Add endpoint**

Add after `/research/query`:

```python
@app.post("/research/assistant", response_model=ResearchAssistantResponse)
def research_assistant(
    request: ResearchAssistantRequest,
    workflow_service: ResearchAssistantWorkflowService = Depends(get_research_assistant_workflow_service),
):
    try:
        return workflow_service.query(
            query=request.query,
            intent=request.intent,
            experiment_log=request.experiment_log,
            top_k=request.top_k,
            idea_count=request.idea_count,
            save_log=request.save_log,
            include_discovery=request.include_discovery,
        )
    except ResearchAssistantWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
```

- [ ] **Step 6: Run API tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_api_mvp.py::test_research_assistant_basic_explore_response backend/src/tests/test_api_mvp.py::test_research_assistant_rejects_blank_query -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/src/main.py backend/src/tests/test_api_mvp.py
git commit -m "feat: expose research assistant endpoint"
```

---

### Task 5: Integration Verification And Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/interview/demo-script.md`
- Test: backend focused and full test suite

- [ ] **Step 1: Run focused tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest \
  backend/src/tests/test_coverage.py \
  backend/src/tests/test_research_assistant_workflow.py \
  backend/src/tests/test_api_mvp.py::test_research_assistant_basic_explore_response \
  backend/src/tests/test_api_mvp.py::test_research_assistant_rejects_blank_query \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run existing adjacent tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest \
  backend/src/tests/test_research_workflow.py \
  backend/src/tests/test_idea_service.py \
  backend/src/tests/test_memory_store.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run full backend tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
```

Expected: PASS.

- [ ] **Step 4: Update README implemented-facts section**

In `README.md`, add a concise implemented-facts bullet only after tests pass:

```markdown
- Agent Workflow entrypoint: `POST /research/assistant` uses a LangGraph thin orchestration layer to route between `basic_explore`, `advanced_ready`, `advanced_search`, and `research_idea`, while reusing existing discovery, knowledge, memory, and idea services.
```

Also keep the limitation explicit:

```markdown
- `/research/assistant` does not implement multi-turn checkpointing, SSE trace streaming, MCP integration, or automatic stale/conflict memory handling.
```

- [ ] **Step 5: Update demo script backend path**

In `docs/interview/demo-script.md`, add a backend-only demo note:

```markdown
`POST /research/assistant` is the Agent Workflow entrypoint. It returns `mode`, `route`, `coverage_score`, `assistant_message`, `next_action`, plus discovery, knowledge, and idea sections. The frontend can be redesigned later around this response, but the first version keeps the backend contract stable.
```

- [ ] **Step 6: Verify docs do not overclaim**

Run:

```bash
rg -n "production-grade|autonomous multi-agent|checkpoint|MCP integration|SSE trace" README.md docs/interview/demo-script.md
```

Expected: either no matches, or matches only in limitations / future-work wording.

- [ ] **Step 7: Commit docs**

```bash
git add README.md docs/interview/demo-script.md
git commit -m "docs: document research assistant workflow endpoint"
```

---

## Final Verification

- [ ] Run full backend tests:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
```

- [ ] Run the offline MVP smoke if the script is present and executable:

```bash
backend/scripts/smoke_offline_mvp.sh
```

- [ ] Check git status:

```bash
git status --short
```

Expected: only intentional untracked or user-owned files remain.

---

## Known Follow-Ups Not In This Plan

- Frontend redesign into a conversational Research Workbench.
- LLM-assisted coverage judge with approximately `0.3` weight.
- `search_plus` after a user selects an idea.
- SSE node progress.
- LangGraph checkpoint / interrupt.
- MCP tools/resources wrapping.
