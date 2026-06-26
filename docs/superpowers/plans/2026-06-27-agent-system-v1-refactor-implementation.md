# Agent System V1 Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the existing `/research/assistant` workflow toward the Agent System V1 architecture: deterministic main-graph routing, subgraph-owned discovery execution, result-summary contracts, stage-level partial errors, grounded `advanced_ready`, and compatibility-safe response migration.

**Architecture:** Keep the existing `build_research_assistant_graph(...)` and `build_paper_discovery_graph(...)` entrypoints. Add typed result contracts and mapping helpers first, then migrate internal graph nodes to emit result summaries and stage-level errors while keeping old public response fields for one compatibility window. The discovery subgraph remains the workflow owner; main graph nodes only dispatch it and aggregate summaries.

**Tech Stack:** Python, FastAPI, Pydantic, LangGraph `StateGraph`, existing discovery/QA/idea services, pytest.

---

## Planning Decisions

1. Keep `/research/assistant` backward compatible until the final response migration task. Existing `discovery`, `knowledge`, and `ideas` fields remain available while new `discovery_result`, `knowledge_result`, and `idea_result` fields are added.
2. Do not add `experiment_log_id` runtime behavior in this implementation. The V1 route rule for this pass is: current request `experiment_log` triggers `research_idea`; stored memory logs do not.
3. Keep `ResearchAssistantWorkflowService.query(...)` as the FastAPI-facing service boundary.
4. Keep discovery pipeline order in `build_paper_discovery_graph(...)` and `graph/nodes.py`. Do not create `DiscoveryService.run_pipeline()`.
5. Use the existing test suite style: fake dependencies in `backend/src/tests/test_research_assistant_workflow.py`, API smoke coverage in `backend/src/tests/test_api_mvp.py`, and discovery graph tests in `backend/src/tests/test_paper_discovery_graph.py`.

## File Structure

- Modify: `backend/src/services/schemas.py`
  - Add V1 result contracts, stage-level error contract, and structured next-action option support.
- Modify: `backend/src/graph/assistant_state.py`
  - Add result-summary fields while keeping legacy fields during migration.
- Modify: `backend/src/graph/assistant_nodes.py`
  - Add mapping helpers, stage-level errors, current-request log routing, memory snapshot pass-through, and grounded `advanced_ready`.
- Modify: `backend/src/services/research_assistant_workflow.py`
  - Initialize new state fields and map graph result into both compatibility fields and V1 result fields.
- Modify: `backend/src/tests/test_research_assistant_workflow.py`
  - Add and update workflow tests for V1 behavior.
- Modify: `backend/src/tests/test_api_mvp.py`
  - Add API response compatibility tests for new fields.
- Inspect: `backend/src/tests/test_paper_discovery_graph.py`
  - Keep existing discovery tests passing. This plan does not require editing this file.

---

### Task 1: Add V1 Contracts With Backward Compatibility

**Files:**
- Modify: `backend/src/services/schemas.py`
- Test: `backend/src/tests/test_research_assistant_workflow.py`

- [ ] **Step 1: Add failing schema compatibility tests**

Append these tests to `backend/src/tests/test_research_assistant_workflow.py`:

```python
from services.schemas import (
    AssistantStageError,
    DiscoveryResult,
    KnowledgeResult,
    NextActionOption,
    ResearchAssistantNextAction,
)


def test_v1_result_contracts_validate_minimal_payloads():
    discovery = DiscoveryResult(enabled=True)
    knowledge = KnowledgeResult(enabled=False)
    error = AssistantStageError(stage="coverage", message="retrieval unavailable")

    assert discovery.top_k == []
    assert discovery.total_raw == 0
    assert knowledge.sources == []
    assert error.recoverable is True


def test_next_action_accepts_structured_options():
    action = ResearchAssistantNextAction(
        type="choose_path",
        options=[
            NextActionOption(
                id="continue_search",
                label="Search papers",
                request_patch={"intent": "search"},
            )
        ],
        message="Choose the next workflow step.",
    )

    assert action.options[0].id == "continue_search"
    assert action.options[0].request_patch == {"intent": "search"}
```

- [ ] **Step 2: Run the new tests and confirm they fail**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py::test_v1_result_contracts_validate_minimal_payloads backend/src/tests/test_research_assistant_workflow.py::test_next_action_accepts_structured_options -q
```

Expected:

```text
ImportError: cannot import name 'AssistantStageError'
```

- [ ] **Step 3: Add contract classes in `services/schemas.py`**

In `backend/src/services/schemas.py`, add these classes after `ResearchQueryResponse` and before the current `ResearchAssistantNextAction` class. Replace the existing `ResearchAssistantNextAction` class with the version below and keep the existing class name:

```python
class AssistantStageError(BaseModel):
    stage: Literal[
        "coverage",
        "query_rewrite",
        "multi_search",
        "postprocess",
        "llm_judge",
        "rank",
        "knowledge_answer",
        "idea_generation",
        "routing",
    ]
    message: str
    recoverable: bool = True


class DiscoveryResult(BaseModel):
    enabled: bool
    top_k: list[dict] = Field(default_factory=list)
    rewritten_queries: list[str] = Field(default_factory=list)
    total_raw: int = 0
    total_deduped: int = 0
    scoring_summary: dict = Field(default_factory=dict)
    error: str | None = None


class KnowledgeResult(BaseModel):
    enabled: bool
    answer: str | None = None
    sources: list[KnowledgeAnswerSource] = Field(default_factory=list)
    mode: str | None = None
    error: str | None = None


class IdeaResult(BaseModel):
    enabled: bool
    ideas: list[IdeaOption] = Field(default_factory=list)
    supporting_evidence: list[IdeaSupportingEvidence] = Field(default_factory=list)
    log_id: int | None = None
    error: str | None = None


class NextActionOption(BaseModel):
    id: str
    label: str
    request_patch: dict = Field(default_factory=dict)
```

Replace the existing `ResearchAssistantNextAction` class with this compatibility version:

```python
class ResearchAssistantNextAction(BaseModel):
    type: Literal["choose_path", "choose_intent", "upload_pdf", "select_idea", "none"]
    options: list[NextActionOption | str] = Field(default_factory=list)
    message: str | None = None
```

Keep the existing `ResearchAssistantError` class unchanged in this task:

```python
class ResearchAssistantError(BaseModel):
    section: Literal["coverage", "discovery", "knowledge", "idea", "routing"]
    message: str
```

Add new result fields to `ResearchAssistantResponse` while keeping legacy fields:

```python
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
    discovery_result: DiscoveryResult = Field(default_factory=lambda: DiscoveryResult(enabled=False))
    knowledge_result: KnowledgeResult = Field(default_factory=lambda: KnowledgeResult(enabled=False))
    idea_result: IdeaResult = Field(default_factory=lambda: IdeaResult(enabled=False))
    discovery: ResearchDiscoverySection
    knowledge: ResearchKnowledgeSection
    ideas: list[IdeaOption] = Field(default_factory=list)
    errors: list[ResearchAssistantError] = Field(default_factory=list)
```

- [ ] **Step 4: Run contract tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py::test_v1_result_contracts_validate_minimal_payloads backend/src/tests/test_research_assistant_workflow.py::test_next_action_accepts_structured_options -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/schemas.py backend/src/tests/test_research_assistant_workflow.py
git commit -m "feat: add assistant v1 result contracts"
```

---

### Task 2: Update Assistant State And Response Initialization

**Files:**
- Modify: `backend/src/graph/assistant_state.py`
- Modify: `backend/src/services/research_assistant_workflow.py`
- Test: `backend/src/tests/test_research_assistant_workflow.py`

- [ ] **Step 1: Write failing response-field test**

Add this test to `backend/src/tests/test_research_assistant_workflow.py`:

```python
def test_assistant_response_includes_v1_result_fields_and_legacy_fields():
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        knowledge_service=FakeKnowledgeQAService(),
    )

    response = service.query(query="graph reconstruction precision", intent="search", top_k=2)

    assert response.discovery.enabled is True
    assert response.knowledge.enabled is True
    assert response.discovery_result.enabled is True
    assert response.knowledge_result.enabled is True
    assert response.idea_result.enabled is False
    assert response.discovery_result.top_k == response.discovery.candidates
    assert response.knowledge_result.answer == response.knowledge.answer
```

- [ ] **Step 2: Run the test and confirm it fails**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py::test_assistant_response_includes_v1_result_fields_and_legacy_fields -q
```

Expected:

```text
AssertionError because response.discovery_result.enabled is still False
```

- [ ] **Step 3: Extend `ResearchAssistantState`**

In `backend/src/graph/assistant_state.py`, replace the class body with:

```python
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
    discovery_result: dict
    knowledge_result: dict
    idea_result: dict
    discovery: dict
    knowledge: dict
    ideas: list[dict]
    assistant_message: str
    next_action: dict | None
    suggested_user_actions: list[str]
    errors: list[dict]
```

- [ ] **Step 4: Initialize new result fields in workflow service**

In `backend/src/services/research_assistant_workflow.py`, import new contracts:

```python
from services.schemas import (
    DiscoveryResult,
    ExperimentLogRequest,
    IdeaResult,
    KnowledgeResult,
    ResearchAssistantError,
    ResearchAssistantNextAction,
    ResearchAssistantResponse,
    ResearchDiscoverySection,
    ResearchKnowledgeSection,
)
```

In the `graph.invoke(...)` initial state, add:

```python
"discovery_result": DiscoveryResult(enabled=False).model_dump(),
"knowledge_result": KnowledgeResult(enabled=False).model_dump(),
"idea_result": IdeaResult(enabled=False).model_dump(),
```

In the `ResearchAssistantResponse(...)` construction, add:

```python
discovery_result=DiscoveryResult(**result["discovery_result"]),
knowledge_result=KnowledgeResult(**result["knowledge_result"]),
idea_result=IdeaResult(**result["idea_result"]),
```

- [ ] **Step 5: Run the new test**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py::test_assistant_response_includes_v1_result_fields_and_legacy_fields -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/graph/assistant_state.py backend/src/services/research_assistant_workflow.py backend/src/tests/test_research_assistant_workflow.py
git commit -m "feat: initialize assistant v1 result state"
```

---

### Task 3: Add Mapping Helpers And Stage-Level Errors

**Files:**
- Modify: `backend/src/services/schemas.py`
- Modify: `backend/src/graph/assistant_nodes.py`
- Modify: `backend/src/tests/test_research_assistant_workflow.py`

- [ ] **Step 1: Update failing tests to assert stage-level errors**

In `backend/src/tests/test_research_assistant_workflow.py`, update these existing assertions:

```python
assert response.errors[0].section == "discovery"
```

to:

```python
assert response.errors[0].stage == "multi_search"
assert response.errors[0].recoverable is True
```

Update:

```python
assert response.errors[0].section == "knowledge"
```

to:

```python
assert response.errors[0].stage == "knowledge_answer"
assert response.errors[0].recoverable is True
```

Update:

```python
assert response.errors[0].section == "coverage"
```

to:

```python
assert response.errors[0].stage == "coverage"
assert response.errors[0].recoverable is True
```

- [ ] **Step 2: Run changed error tests and confirm they fail**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py::test_search_intent_routes_to_advanced_search_and_preserves_partial_discovery_failure backend/src/tests/test_research_assistant_workflow.py::test_search_intent_calls_answer_once_when_route_consumes_knowledge backend/src/tests/test_research_assistant_workflow.py::test_auto_coverage_retrieval_failure_routes_to_basic_explore_with_coverage_error -q
```

Expected:

```text
AttributeError: 'ResearchAssistantError' object has no attribute 'stage'
```

The expected failure comes from tests asking for `stage` while graph nodes still emit `section`.

- [ ] **Step 3: Add helper functions in `assistant_nodes.py`**

In `backend/src/services/schemas.py`, replace the existing `ResearchAssistantError` class with:

```python
class ResearchAssistantError(AssistantStageError):
    pass
```

In `backend/src/graph/assistant_nodes.py`, update imports:

```python
from services.schemas import (
    DiscoveryResult,
    IdeaResult,
    KnowledgeResult,
    ResearchDiscoverySection,
    ResearchKnowledgeSection,
)
```

Add these helpers near the bottom of the file, before `_semantic_memory_text(...)`:

```python
def _stage_error(stage: str, message: str, recoverable: bool = True) -> dict:
    return {"stage": stage, "message": message, "recoverable": recoverable}


def _discovery_result_from_section(
    discovery: ResearchDiscoverySection,
    rewritten_queries: list[str] | None = None,
    total_raw: int = 0,
    total_deduped: int = 0,
    ranked_count: int | None = None,
) -> DiscoveryResult:
    candidates = discovery.candidates
    return DiscoveryResult(
        enabled=discovery.enabled,
        top_k=candidates,
        rewritten_queries=rewritten_queries or [],
        total_raw=total_raw,
        total_deduped=total_deduped,
        scoring_summary={"ranked_count": ranked_count if ranked_count is not None else len(candidates)},
        error=discovery.error,
    )


def _knowledge_result_from_section(knowledge: ResearchKnowledgeSection) -> KnowledgeResult:
    return KnowledgeResult(
        enabled=knowledge.enabled,
        answer=knowledge.answer,
        sources=knowledge.sources,
        mode=knowledge.mode,
        error=knowledge.error,
    )


def _empty_idea_result() -> IdeaResult:
    return IdeaResult(enabled=False)
```

- [ ] **Step 4: Replace emitted error dictionaries**

In `assess_query_coverage`, replace:

```python
errors = errors + [{"section": "coverage", "message": exc.detail}]
```

with:

```python
errors = errors + [_stage_error("coverage", exc.detail)]
```

In `run_research_idea`, replace:

```python
{"section": "idea", "message": "experiment_log is required for research intent"}
```

with:

```python
_stage_error("idea_generation", "experiment_log is required for research intent", recoverable=False)
```

Replace:

```python
{"section": "idea", "message": exc.detail}
```

with:

```python
_stage_error("idea_generation", exc.detail)
```

In `_run_discovery`, replace:

```python
[{"section": "discovery", "message": message}]
```

with:

```python
[_stage_error("multi_search", message)]
```

In `_run_knowledge`, replace:

```python
[{"section": "knowledge", "message": exc.detail}]
```

with:

```python
[_stage_error("knowledge_answer", exc.detail)]
```

In `_knowledge_from_state_or_service`, replace:

```python
return knowledge, [{"section": "knowledge", "message": knowledge.error}]
```

with:

```python
return knowledge, [_stage_error("knowledge_answer", knowledge.error)]
```

- [ ] **Step 5: Update route nodes to populate result fields**

In `run_basic_explore`, add these returned fields:

```python
"discovery_result": _discovery_result_from_section(discovery).model_dump(),
"knowledge_result": _knowledge_result_from_section(knowledge).model_dump(),
"idea_result": _empty_idea_result().model_dump(),
```

In `run_advanced_search`, add the same three fields.

In `run_advanced_ready`, return:

```python
"discovery_result": DiscoveryResult(enabled=False).model_dump(),
"knowledge_result": KnowledgeResult(enabled=False).model_dump(),
"idea_result": _empty_idea_result().model_dump(),
```

In `run_research_idea`, return:

```python
"discovery_result": _discovery_result_from_section(
    ResearchDiscoverySection(
        enabled=response.discovery.enabled,
        candidates=response.discovery.candidates,
        error=response.discovery.error,
    )
).model_dump(),
"knowledge_result": _knowledge_result_from_section(
    ResearchKnowledgeSection(
        enabled=True,
        answer=None,
        sources=response.knowledge.sources,
        error=response.knowledge.error,
        mode=response.mode,
    )
).model_dump(),
"idea_result": IdeaResult(
    enabled=True,
    ideas=response.ideas,
    supporting_evidence=[
        evidence
        for idea in response.ideas
        for evidence in idea.supporting_evidence
    ],
    log_id=response.log_id,
    error=None,
).model_dump(),
```

- [ ] **Step 6: Run assistant workflow tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 7: Commit**

```bash
git add backend/src/services/schemas.py backend/src/graph/assistant_nodes.py backend/src/tests/test_research_assistant_workflow.py
git commit -m "feat: add assistant stage errors and result mapping"
```

---

### Task 4: Fix Current-Request Experiment Log Routing

**Files:**
- Modify: `backend/src/graph/assistant_nodes.py`
- Modify: `backend/src/services/research_assistant_workflow.py`
- Modify: `backend/src/tests/test_research_assistant_workflow.py`

- [ ] **Step 1: Add routing tests**

Append these tests to `backend/src/tests/test_research_assistant_workflow.py`:

```python
def test_experiment_log_triggers_research_idea_even_when_intent_is_auto():
    idea_service = FakeIdeaService()
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        idea_service=idea_service,
    )

    response = service.query(
        query="graph reconstruction precision",
        intent="auto",
        experiment_log=make_log(),
    )

    assert response.route == "research_idea"
    assert len(idea_service.calls) == 1


def test_stored_memory_log_does_not_trigger_research_idea_without_current_request_log():
    idea_service = FakeIdeaService()
    service = build_service(
        store=FakeStore(
            "Confirmed semantic memory: graph reconstruction precision\n"
            "Recent episodic memory: task=graph reconstruction observation=precision drops"
        ),
        idea_service=idea_service,
    )

    response = service.query(query="graph reconstruction precision", intent="auto")

    assert response.route == "advanced_ready"
    assert idea_service.calls == []
```

- [ ] **Step 2: Run routing tests and confirm first test fails**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py::test_experiment_log_triggers_research_idea_even_when_intent_is_auto backend/src/tests/test_research_assistant_workflow.py::test_stored_memory_log_does_not_trigger_research_idea_without_current_request_log -q
```

Expected:

```text
1 failed, 1 passed
```

- [ ] **Step 3: Allow auto intent with experiment_log in workflow service**

In `backend/src/services/research_assistant_workflow.py`, keep this validation:

```python
if intent == "research" and experiment_log is None:
    raise ResearchAssistantWorkflowError("experiment_log is required for research intent", status_code=400)
```

Do not add validation that blocks `intent="auto"` with an experiment log.

- [ ] **Step 4: Update `route_request`**

In `backend/src/graph/assistant_nodes.py`, replace `route_request` with:

```python
def route_request(state: dict) -> dict:
    intent = state["intent"]
    if state.get("experiment_log") is not None:
        return {
            "mode": "advanced",
            "route": "research_idea",
            "route_reason": "current request includes an experiment log",
        }
    if intent == "research":
        return {
            "mode": "advanced",
            "route": "research_idea",
            "route_reason": "research intent requested idea generation",
        }
    if intent == "search":
        return {
            "mode": "advanced",
            "route": "advanced_search",
            "route_reason": "search intent requested contextual discovery and grounded QA",
        }
    if state["coverage_score"] >= ADVANCED_THRESHOLD:
        return {"mode": "advanced", "route": "advanced_ready"}
    return {"mode": "basic", "route": "basic_explore"}
```

- [ ] **Step 5: Run routing tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py::test_experiment_log_triggers_research_idea_even_when_intent_is_auto backend/src/tests/test_research_assistant_workflow.py::test_stored_memory_log_does_not_trigger_research_idea_without_current_request_log -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/graph/assistant_nodes.py backend/src/services/research_assistant_workflow.py backend/src/tests/test_research_assistant_workflow.py
git commit -m "fix: route current request experiment logs to ideas"
```

---

### Task 5: Enforce Discovery Boundary And Memory Snapshot Pass-Through

**Files:**
- Modify: `backend/src/graph/assistant_nodes.py`
- Modify: `backend/src/tests/test_research_assistant_workflow.py`

- [ ] **Step 1: Add memory pass-through test**

Append this test to `backend/src/tests/test_research_assistant_workflow.py`:

```python
def test_discovery_subgraph_receives_main_graph_memory_snapshot():
    discovery = FakeDiscoveryGraph()
    memory_context = "Confirmed semantic memory: graph reconstruction precision"
    service = build_service(
        store=FakeStore(memory_context),
        discovery_graph=discovery,
        knowledge_service=FakeKnowledgeQAService(),
    )

    response = service.query(query="graph reconstruction precision", intent="search")

    assert response.route == "advanced_search"
    assert discovery.calls[0]["memory_context"] == memory_context
```

- [ ] **Step 2: Add result summary count test**

Append:

```python
def test_discovery_result_contains_summary_counts_without_exposing_raw_results_on_main_state():
    discovery = FakeDiscoveryGraph(
        result=[
            {"paper": {"paper_id": "d1", "title": "Discovery One"}},
            {"paper": {"paper_id": "d2", "title": "Discovery Two"}},
        ]
    )
    service = build_service(discovery_graph=discovery, knowledge_service=FakeKnowledgeQAService())

    response = service.query(query="new topic", intent="search", top_k=1)

    assert response.discovery_result.enabled is True
    assert len(response.discovery_result.top_k) == 1
    assert response.discovery_result.scoring_summary["ranked_count"] == 2
```

- [ ] **Step 3: Run tests and confirm memory test fails**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py::test_discovery_subgraph_receives_main_graph_memory_snapshot backend/src/tests/test_research_assistant_workflow.py::test_discovery_result_contains_summary_counts_without_exposing_raw_results_on_main_state -q
```

Expected:

```text
1 failed, 1 passed
```

- [ ] **Step 4: Update `_run_discovery` to return metadata**

In `backend/src/graph/assistant_nodes.py`, replace `_run_discovery` with this version:

```python
def _run_discovery(discovery_graph, state: dict, enabled: bool) -> tuple[ResearchDiscoverySection, list[dict], dict]:
    if not enabled:
        return ResearchDiscoverySection(enabled=False), [], {"ranked_count": 0}
    try:
        result = discovery_graph.invoke(
            {
                "mode": state["mode"],
                "user_query": state["query"],
                "memory_context": state["memory_context"],
                "rewritten_queries": [],
                "raw_results": [],
                "normalized_papers": [],
                "deduped_papers": [],
                "judge_results": [],
                "ranked_candidates": [],
            }
        )
        ranked_candidates = result["ranked_candidates"]
        metadata = {
            "rewritten_queries": result.get("rewritten_queries", []),
            "total_raw": len(result.get("raw_results", [])),
            "total_deduped": len(result.get("deduped_papers", [])),
            "ranked_count": len(ranked_candidates),
        }
        return ResearchDiscoverySection(
            enabled=True,
            candidates=ranked_candidates[: state["top_k"]],
            error=None,
        ), [], metadata
    except Exception as exc:
        message = str(exc)
        return ResearchDiscoverySection(enabled=True, candidates=[], error=message), [
            _stage_error("multi_search", message)
        ], {"ranked_count": 0}
```

Update `run_basic_explore` and `run_advanced_search` callers from:

```python
discovery, errors = _run_discovery(discovery_graph, state, enabled=True)
```

to:

```python
discovery, errors, discovery_metadata = _run_discovery(discovery_graph, state, enabled=True)
```

Update `discovery_result` construction:

```python
"discovery_result": _discovery_result_from_section(
    discovery,
    rewritten_queries=discovery_metadata.get("rewritten_queries", []),
    total_raw=discovery_metadata.get("total_raw", 0),
    total_deduped=discovery_metadata.get("total_deduped", 0),
    ranked_count=discovery_metadata.get("ranked_count", 0),
).model_dump(),
```

- [ ] **Step 5: Run boundary tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py::test_discovery_subgraph_receives_main_graph_memory_snapshot backend/src/tests/test_research_assistant_workflow.py::test_discovery_result_contains_summary_counts_without_exposing_raw_results_on_main_state -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/graph/assistant_nodes.py backend/src/tests/test_research_assistant_workflow.py
git commit -m "fix: pass assistant memory snapshot to discovery subgraph"
```

---

### Task 6: Convert advanced_ready To Grounded QA Plus Guidance

**Files:**
- Modify: `backend/src/graph/assistant_nodes.py`
- Modify: `backend/src/tests/test_research_assistant_workflow.py`

- [ ] **Step 1: Replace existing advanced_ready test expectations**

Update `test_auto_high_coverage_routes_to_advanced_ready_without_running_discovery` so the assertions become:

```python
assert response.mode == "advanced"
assert response.route == "advanced_ready"
assert response.discovery.enabled is False
assert response.knowledge.enabled is True
assert response.knowledge.answer == "Knowledge answer"
assert response.knowledge_result.enabled is True
assert response.knowledge_result.answer == "Knowledge answer"
assert discovery.calls == []
assert knowledge.retrieval_service.calls == [("graph reconstruction precision", 5)]
assert knowledge.answer_calls == [("graph reconstruction precision", 5)]
assert response.next_action is not None
assert response.next_action.type == "choose_path"
```

- [ ] **Step 2: Add no-source fallback test**

Append:

```python
def test_advanced_ready_returns_no_source_fallback_when_qa_has_no_sources():
    knowledge = FakeKnowledgeQAService(
        response=KnowledgeAnswerResponse(
            question="graph reconstruction precision",
            answer="No relevant knowledge chunks were found.",
            sources=[],
            mode="deterministic",
        )
    )
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        knowledge_service=knowledge,
    )

    response = service.query(query="graph reconstruction precision", intent="auto", top_k=5)

    assert response.route == "advanced_ready"
    assert response.knowledge.enabled is True
    assert response.knowledge.sources == []
    assert "could not find grounded local sources" in response.assistant_message.lower()
    assert response.next_action is not None
    assert response.next_action.type == "choose_path"
```

- [ ] **Step 3: Run advanced_ready tests and confirm failure**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py::test_auto_high_coverage_routes_to_advanced_ready_without_running_discovery backend/src/tests/test_research_assistant_workflow.py::test_advanced_ready_returns_no_source_fallback_when_qa_has_no_sources -q
```

Expected:

```text
tests fail because advanced_ready does not call KnowledgeQAService.answer
```

- [ ] **Step 4: Replace `run_advanced_ready`**

In `backend/src/graph/assistant_nodes.py`, replace `run_advanced_ready` with:

```python
def run_advanced_ready(state: dict) -> dict:
    knowledge, knowledge_errors = _knowledge_from_state_or_service(knowledge_qa_service, state, enabled=True)
    if knowledge.sources:
        assistant_message = (
            "I found grounded local knowledge for this query and returned an answer. "
            "You can continue with paper search or submit a new experiment log for idea recommendations."
        )
    else:
        assistant_message = (
            "This query matches your existing research context, but I could not find grounded local sources "
            "for a reliable answer. You can continue with paper search or submit a new experiment log."
        )
    return {
        "discovery": ResearchDiscoverySection(enabled=False).model_dump(),
        "knowledge": knowledge.model_dump(),
        "discovery_result": DiscoveryResult(enabled=False).model_dump(),
        "knowledge_result": _knowledge_result_from_section(knowledge).model_dump(),
        "idea_result": _empty_idea_result().model_dump(),
        "assistant_message": assistant_message,
        "next_action": {
            "type": "choose_path",
            "options": [
                {
                    "id": "continue_search",
                    "label": "Search papers",
                    "request_patch": {"intent": "search"},
                },
                {
                    "id": "submit_experiment_log",
                    "label": "Submit experiment log",
                    "request_patch": {"intent": "research"},
                },
            ],
            "message": "Choose the next workflow step.",
        },
        "suggested_user_actions": [
            "Continue with search for contextual paper recommendations.",
            "Submit a structured experiment log for idea recommendations.",
        ],
        "errors": state["errors"] + knowledge_errors,
    }
```

- [ ] **Step 5: Run advanced_ready tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py::test_auto_high_coverage_routes_to_advanced_ready_without_running_discovery backend/src/tests/test_research_assistant_workflow.py::test_advanced_ready_returns_no_source_fallback_when_qa_has_no_sources -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/graph/assistant_nodes.py backend/src/tests/test_research_assistant_workflow.py
git commit -m "feat: ground advanced ready responses"
```

---

### Task 7: Normalize next_action Options In Compatibility Layer

**Files:**
- Modify: `backend/src/services/schemas.py`
- Modify: `backend/src/services/research_assistant_workflow.py`
- Modify: `backend/src/graph/assistant_nodes.py`
- Modify: `backend/src/tests/test_research_assistant_workflow.py`

- [ ] **Step 1: Add next_action structure test**

Append this test:

```python
def test_next_action_options_are_structured_in_response():
    service = build_service(
        store=FakeStore("Confirmed semantic memory: graph reconstruction precision"),
        knowledge_service=FakeKnowledgeQAService(),
    )

    response = service.query(query="graph reconstruction precision", intent="auto")

    assert response.next_action is not None
    assert response.next_action.options[0].id == "continue_search"
    assert response.next_action.options[0].request_patch == {"intent": "search"}
```

- [ ] **Step 2: Run the test and confirm it fails before normalization**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py::test_next_action_options_are_structured_in_response -q
```

Expected:

```text
test fails because at least one route still returns string options or mixed option types
```

- [ ] **Step 3: Add normalization helper**

In `backend/src/services/research_assistant_workflow.py`, import `NextActionOption`:

```python
from services.schemas import (
    DiscoveryResult,
    ExperimentLogRequest,
    IdeaResult,
    KnowledgeResult,
    NextActionOption,
    ResearchAssistantError,
    ResearchAssistantNextAction,
    ResearchAssistantResponse,
    ResearchDiscoverySection,
    ResearchKnowledgeSection,
)
```

Add this helper below `ResearchAssistantWorkflowError`:

```python
def _normalize_next_action(action: dict | None) -> ResearchAssistantNextAction | None:
    if action is None:
        return None
    normalized_options = []
    for option in action.get("options", []):
        if isinstance(option, dict):
            normalized_options.append(NextActionOption(**option))
        else:
            normalized_options.append(
                NextActionOption(
                    id=str(option),
                    label=str(option).replace("_", " ").title(),
                    request_patch={},
                )
            )
    return ResearchAssistantNextAction(
        type=action["type"],
        options=normalized_options,
        message=action.get("message"),
    )
```

In `ResearchAssistantResponse(...)`, replace:

```python
next_action=(
    ResearchAssistantNextAction(**result["next_action"])
    if result.get("next_action") is not None
    else None
),
```

with:

```python
next_action=_normalize_next_action(result.get("next_action")),
```

In `backend/src/services/schemas.py`, tighten `ResearchAssistantNextAction.options` from:

```python
options: list[NextActionOption | str] = Field(default_factory=list)
```

to:

```python
options: list[NextActionOption] = Field(default_factory=list)
```

- [ ] **Step 4: Update node output strings only where useful**

For `run_basic_explore`, keep `type="upload_pdf"` but replace options with:

```python
"options": [
    {"id": "review_candidates", "label": "Review candidates", "request_patch": {}},
    {"id": "upload_pdf", "label": "Upload PDF", "request_patch": {}},
],
```

For `run_advanced_search`, keep `type="none"` and `options=[]`.

For `run_research_idea`, replace options with:

```python
"options": [
    {"id": "select_idea", "label": "Select idea", "request_patch": {}},
    {"id": "continue_search", "label": "Continue search", "request_patch": {"intent": "search"}},
],
```

- [ ] **Step 5: Run assistant workflow tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/services/schemas.py backend/src/services/research_assistant_workflow.py backend/src/graph/assistant_nodes.py backend/src/tests/test_research_assistant_workflow.py
git commit -m "feat: normalize assistant next actions"
```

---

### Task 8: Add API Contract Coverage

**Files:**
- Modify: `backend/src/tests/test_api_mvp.py`

- [ ] **Step 1: Update existing assistant API tests**

In `backend/src/tests/test_api_mvp.py`, update `test_research_assistant_basic_explore_response` after the existing `body["next_action"]["type"]` assertion with:

```python
assert body["discovery_result"]["enabled"] is True
assert body["knowledge_result"]["enabled"] is True
assert body["idea_result"]["enabled"] is False
assert body["discovery_result"]["top_k"] == body["discovery"]["candidates"]
assert body["knowledge_result"]["answer"] == body["knowledge"]["answer"]
assert isinstance(body["errors"], list)
```

In `test_research_assistant_research_include_discovery_uses_default_dependency_graph`, after the existing discovery candidate assertion, add:

```python
assert body["discovery_result"]["enabled"] is True
assert body["idea_result"]["enabled"] is True
assert body["idea_result"]["ideas"][0]["title"]
```

- [ ] **Step 2: Add shared shape assertions**

In both updated tests, add these top-level assertions after `body = response.json()`:

```python
assert "discovery_result" in body
assert "knowledge_result" in body
assert "idea_result" in body
assert "discovery" in body
assert "knowledge" in body
assert "ideas" in body
assert isinstance(body["errors"], list)
```

- [ ] **Step 3: Run API tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_api_mvp.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 4: Commit**

```bash
git add backend/src/tests/test_api_mvp.py
git commit -m "test: cover assistant v1 api fields"
```

---

### Task 9: Service Boundary Audit

**Files:**
- Inspect: `backend/src/services/*.py`
- Inspect: `backend/src/graph/*.py`
- Modify: `docs/superpowers/plans/2026-06-27-agent-system-v1-refactor-implementation.md`

- [ ] **Step 1: Search for discovery pipeline duplication**

Run:

```bash
rg -n "DiscoveryService|run_pipeline|execute_pipeline|multi_search.*rank|rewrite.*search.*rank" backend/src
```

Expected:

```text
no service owns the full rewrite -> search -> postprocess -> judge -> rank pipeline
```

- [ ] **Step 2: Record audit result**

Append this audit note under this task after running the search:

```markdown
Audit result:
- Full discovery pipeline service found: no
- Discovery workflow owner remains: `build_paper_discovery_graph(...)`
- Atomic services remain in: `backend/src/services/`
```

- [ ] **Step 3: Commit audit note**

```bash
git add docs/superpowers/plans/2026-06-27-agent-system-v1-refactor-implementation.md
git commit -m "docs: record assistant v1 service boundary audit"
```

---

### Task 10: Full Verification

**Files:**
- Inspect current worktree and test output.

- [ ] **Step 1: Run assistant workflow tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_assistant_workflow.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 2: Run discovery graph tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_paper_discovery_graph.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 3: Run backend tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 4: Run offline smoke**

Run:

```bash
backend/scripts/smoke_offline_mvp.sh
```

Expected:

```text
OFFLINE_MVP_SMOKE_OK=true
```

- [ ] **Step 5: Run diff hygiene**

Run:

```bash
git diff --check
```

Expected:

```text
no output
```

- [ ] **Step 6: Record final verification output in the implementation summary**

Add the exact commands run and their pass/fail results to the final assistant response for the implementation run. Do not create a verification-only commit when no files changed.

---

## Execution Handoff

Recommended execution mode: **Subagent-Driven** for Tasks 1-8, with direct review after each task. Task 9 is an audit task and can be handled inline. Task 10 should be run by the main agent before declaring completion.

Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, and keep commits small.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batching only after tests pass at each checkpoint.
