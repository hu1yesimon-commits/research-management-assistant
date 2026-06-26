# Agent System V1 Refactor Design

日期：2026-06-27

> 本文档是 Agent System V1 重构的冻结架构定义。它描述下一阶段工程落地目标，不表示当前代码已经完全实现。实现时必须保持默认可解释、可测试、可降级，并避免把系统包装成不可控的 autonomous agent。

## 1. System Positioning

V1 is a LangGraph-based research workflow system where routing is deterministic and handled by the main graph, discovery is executed through a subgraph-owned pipeline, and retrieval, scoring, ranking, QA, memory, and idea generation are implemented as modular service components.

系统中文定义：

```text
一个基于 LangGraph 的 Research Assistant System，通过 Main Graph routing、Discovery Subgraph workflow、atomic services 和 structured feature state，实现可解释的论文检索、知识问答与研究 idea 生成工作流。
```

## 2. Immutable V1 Principles

1. `LangGraph Main Graph` owns control flow and orchestration.
2. `Subgraph` owns workflow execution order.
3. `Service` owns atomic computation only.
4. `State` is a structured feature store, not an event log.
5. `LLM` is used for feature enrichment and generation, not routing control.

## 3. Layered Architecture

```text
User Request
  -> LangGraph Main Graph
       - load memory snapshot
       - assess coverage
       - deterministic route
       - dispatch selected workflow
       - aggregate result summaries
       - produce next_action
  -> Discovery Subgraph OR Knowledge QA OR Idea Service
  -> Atomic Services
       - query rewrite
       - multi search
       - postprocess
       - LLM judge
       - rank
       - grounded answer
       - idea generation
  -> Structured Response
```

### 3.1 Main Graph: Control Layer

Responsibilities:

- routing decision
- workflow orchestration
- context snapshot management
- result aggregation
- `next_action` generation
- partial failure aggregation

Nodes:

- `load_memory_context`
- `assess_coverage`
- `route_request`
- `basic_explore`
- `advanced_search`
- `research_idea`
- `advanced_ready`

Main graph must not inspect raw retrieval internals. It consumes typed summaries only:

- `discovery_result`
- `knowledge_result`
- `idea_result`

### 3.2 Discovery Subgraph: Workflow Layer

Discovery Subgraph is the full pipeline owner:

```text
query_rewrite
  -> multi_search
  -> postprocess
  -> llm_judge
  -> rank
  -> top_k output
```

Subgraph responsibilities:

- express discovery workflow structure
- preserve traceable execution order
- keep intermediate candidate state private
- emit a compact `DiscoveryResult` contract to the main graph

The subgraph owns workflow execution. Services do not decide step order.

### 3.3 Service Layer: Compute Layer

Atomic service responsibilities:

- `QueryRewriteService`: generate retrieval queries.
- `MultiSearchService`: retrieve papers from configured sources.
- `PostProcessService`: normalize, clean, deduplicate, and compute rule features.
- `LLMJudgeService`: produce semantic relevance features.
- `RankerService`: aggregate scoring features into final scores.
- `KnowledgeQAService`: produce grounded answers from local knowledge sources.
- `IdeaService`: generate research ideas from current-request experiment evidence.
- `MemoryStore`: provide a request-scoped memory snapshot.

Service constraints:

- Services must not decide workflow order.
- Services must not modify routing state.
- No service should duplicate the full Discovery Subgraph pipeline. If a legacy `DiscoveryService` remains temporarily, it may only act as a compatibility facade and must not become the pipeline owner.

## 4. State Model

### 4.1 State Rules

State is a feature store. It stores structured information needed by later nodes or the response layer.

The append-only rule applies selectively:

- Candidate feature enrichment inside the subgraph should be append-only.
- `errors` should be append-only.
- Main graph result fields are request-scoped outputs and may be overwritten by the selected route.

### 4.2 Main State

Target main state:

```python
ResearchAssistantState:
    # Input
    query
    intent
    experiment_log
    experiment_log_id

    # Control
    route
    coverage_score
    route_reason

    # Memory Snapshot
    memory_context
    semantic_memory
    recent_logs

    # Result Summaries
    discovery_result
    knowledge_result
    idea_result

    # Interaction
    assistant_message
    next_action

    # Partial Failures
    errors
```

Main state must not store:

- raw search results
- raw candidates
- normalized intermediate papers
- deduped intermediate papers
- per-step judge internals beyond result summaries

### 4.3 Subgraph State

Target discovery subgraph state:

```python
DiscoverySubgraphState:
    user_query
    memory_context
    rewritten_queries
    raw_results
    normalized_candidates
    deduped_candidates
    candidates
    ranked_candidates
```

Candidate feature schema:

```python
CandidateFeatures:
    embedding_relevance_score
    llm_relevance_score
    quality_score
    novelty_score
    rule_score
    final_score
```

### 4.4 Parent-Child Boundary Contract

The main graph needs enough information to aggregate a response, but not enough to couple itself to discovery internals.

Target `DiscoveryResult`:

```python
DiscoveryResult:
    enabled
    top_k
    rewritten_queries
    total_raw
    total_deduped
    scoring_summary
    error
```

`top_k` contains user-visible ranked candidates. It is not considered raw internal state. Raw results, dedupe intermediates, and internal judge batches remain subgraph-private.

Target `KnowledgeResult`:

```python
KnowledgeResult:
    enabled
    answer
    sources
    mode
    error
```

Target `IdeaResult`:

```python
IdeaResult:
    enabled
    ideas
    supporting_evidence
    log_id
    error
```

## 5. Routing Policy

Routing is deterministic. LLM output must not control route selection.

Target route logic:

```text
IF current request contains experiment_log OR experiment_log_id:
    -> research_idea
ELSE IF intent == "search":
    -> advanced_search
ELSE IF coverage_score < threshold:
    -> basic_explore
ELSE:
    -> advanced_ready
```

Route meanings:

| Route | Meaning |
| --- | --- |
| `basic_explore` | New or under-covered research area. Run discovery and grounded QA fallback. |
| `advanced_search` | User explicitly wants contextual paper search and grounded QA. |
| `research_idea` | Current request contains experiment evidence and asks for idea generation. |
| `advanced_ready` | Existing context appears sufficient; answer if grounded and guide next step. |

### 5.1 Experiment Log Trigger Semantics

`experiment_log` is an event trigger, not a persistent condition.

Rules:

- A current request body containing `experiment_log` triggers `research_idea`.
- A current request body containing an explicit `experiment_log_id` triggers `research_idea`.
- Previously stored logs are memory context only and must not automatically trigger `research_idea`.
- Freshness is auxiliary metadata for UI defaults, memory weighting, and duplicate prevention. It is not the primary route trigger.

Recommended future metadata:

```python
ExperimentLogRoutingMetadata:
    experiment_log_id
    experiment_log_created_at
    idea_generated_at
    processed_in_session
```

This prevents old stored logs from repeatedly forcing idea recommendations while preserving an explicit path for reusing an older log when the user asks for it.

## 6. LLM Role

LLM may do:

1. Query rewrite.
2. Candidate semantic feature generation through LLM judge.
3. Research idea generation from current experiment evidence.
4. Grounded answer synthesis only when local knowledge sources are present.

LLM must not do:

- routing control
- final ranking authority
- system planning
- answer generation without source grounding

## 7. Scoring

LLM judge is a feature generator, not the ranking authority.

Target candidate scoring:

```text
final_score = weighted_sum(
    embedding_relevance_score,
    llm_relevance_score,
    quality_score,
    novelty_score,
    rule_score
)
```

The ranker owns final aggregation. If LLM relevance has a high weight, docs and interview explanation must say it is a strong feature, not the sole authority.

## 8. Route Behaviors

### 8.1 `basic_explore`

Runs:

- Discovery Subgraph
- Knowledge QA with no-source fallback

Returns:

- `discovery_result.top_k`
- `knowledge_result`
- next action guiding the user to review papers and upload PDFs

### 8.2 `advanced_search`

Runs:

- Discovery Subgraph with memory context
- Knowledge QA

Returns:

- contextual discovery candidates
- grounded answer if sources exist
- next action for accepting papers, uploading PDFs, or submitting an experiment log

### 8.3 `research_idea`

Runs:

- Idea Service
- optional retrieval/discovery evidence depending on request flags

Returns:

- idea options
- supporting evidence
- next action for selecting an idea or continuing search

### 8.4 `advanced_ready`

`advanced_ready` is not a pause node.

It is a hybrid answer-and-guide node:

```text
if knowledge sources exist:
    return grounded QA + next_action
else:
    return explicit no-grounded-answer message + next_action
```

Its purpose is to answer when the local knowledge base can ground the response, while still guiding the user toward either paper search or experiment-log-based idea generation.

## 9. next_action

V1 `next_action` is a stateless interaction contract.

It supports:

- UI guidance
- next-step options
- request patch hints for future UI wiring

It does not support:

- LangGraph checkpoint
- session resume
- multi-turn orchestration

Target shape:

```json
{
  "type": "choose_path",
  "options": [
    {
      "id": "continue_search",
      "label": "Search papers",
      "request_patch": {
        "intent": "search"
      }
    },
    {
      "id": "submit_experiment_log",
      "label": "Submit experiment log",
      "request_patch": {
        "intent": "research"
      }
    }
  ],
  "message": "Choose the next workflow step."
}
```

The current implementation may keep string options temporarily, but the migration target is structured options.

## 10. errors

`errors` is the partial failure isolation layer.

Target shape:

```json
{
  "stage": "llm_judge",
  "message": "timeout",
  "recoverable": true
}
```

Rules:

- Recoverable stage failures should not abort the full graph.
- Errors should identify the failing stage, not only the broad section.
- The response should remain structurally valid even when one stage fails.

Recommended stages:

- `coverage`
- `query_rewrite`
- `multi_search`
- `postprocess`
- `llm_judge`
- `rank`
- `knowledge_answer`
- `idea_generation`
- `routing`

## 11. Engineering Migration Scope

The current code already has a useful starting point:

- `build_paper_discovery_graph(...)` already expresses the discovery pipeline as a subgraph.
- `build_research_assistant_graph(...)` already expresses the four main routes.
- Existing service modules already cover search, query rewrite, judge, scoring, QA, memory, and idea generation.

The V1 refactor should focus on boundary correction, not a wholesale rewrite.

Required migration areas:

1. Rename or map response fields from `discovery/knowledge/ideas` toward `discovery_result/knowledge_result/idea_result`.
2. Update error schema from broad `section` to stage-level `stage/message/recoverable`.
3. Update `route_request` so current-request experiment logs trigger `research_idea`; stored logs do not.
4. Update `advanced_ready` to perform grounded QA when sources exist and produce a no-source fallback otherwise.
5. Pass the main graph memory snapshot into the discovery subgraph instead of letting the subgraph silently rebuild an unrelated snapshot.
6. Split or wrap service responsibilities so no `DiscoveryService` owns the full pipeline order.
7. Add tests for routing, boundary contracts, partial failure, and advanced-ready grounded answer behavior.

## 12. Codebase Mapping

This section maps the V1 architecture to the current repository so an implementation plan can be written at PR level.

### 12.1 Current Files

| V1 Concept | Current Location | Migration Notes |
| --- | --- | --- |
| Main graph builder | `backend/src/graph/builder.py` | `build_research_assistant_graph(...)` already exists and should remain the main graph entry. |
| Main graph nodes | `backend/src/graph/assistant_nodes.py` | Update routing, `advanced_ready`, discovery boundary mapping, and stage-level errors here. |
| Main state | `backend/src/graph/assistant_state.py` | Rename or map `discovery/knowledge/ideas` toward result-summary fields. Keep compatibility during migration. |
| Discovery subgraph builder | `backend/src/graph/builder.py` | `build_paper_discovery_graph(...)` already owns the discovery order. Keep this ownership. |
| Discovery subgraph nodes | `backend/src/graph/nodes.py` | Keep rewrite, search, postprocess, judge, and rank as subgraph nodes. Avoid moving this order into a service. |
| Discovery subgraph state | `backend/src/graph/state.py` | Keep intermediate discovery fields here, not in main state. |
| Request/response schemas | `backend/src/services/schemas.py` | Add result contracts, structured next-action options, and stage-level error schema. |
| Workflow service wrapper | `backend/src/services/research_assistant_workflow.py` | Keep FastAPI-to-graph translation here. Add compatibility mapping if response field names change. |
| Query rewrite | `backend/src/services/query_rewriter.py` | Treat as atomic computation. |
| Multi-source search | `backend/src/services/paper_search.py` and `backend/src/services/adapters/` | Treat as atomic computation. |
| Postprocess | `backend/src/services/normalizer.py`, `backend/src/services/deduplicator.py` | Treat normalization and dedupe as atomic computation. |
| LLM judge | `backend/src/services/LlmPaperSelect.py` | Treat as feature generation only. Do not give it route control. |
| Scoring/ranking | `backend/src/services/scoreutils.py`, `backend/src/graph/nodes.py` | Rank aggregation remains deterministic and inspectable. |
| Knowledge QA | `backend/src/services/qa_service.py`, `backend/src/services/answer_service.py` | Use only when sources exist; keep no-source fallback explicit. |
| Idea generation | `backend/src/services/idea_service.py` | Trigger only from current-request `experiment_log` or explicit future `experiment_log_id`. |
| API route | `backend/src/main.py` | Keep `/research/assistant` as the Agent Workflow endpoint. |
| Assistant tests | `backend/src/tests/test_research_assistant_workflow.py`, `backend/src/tests/test_api_mvp.py` | Extend for routing, result contracts, errors, and `advanced_ready`. |
| Discovery tests | `backend/src/tests/test_paper_discovery_graph.py` | Extend for parent-child memory snapshot and result summary. |

### 12.2 Preferred File Additions

The implementation may add small schema-focused files if `services/schemas.py` becomes too large:

- `backend/src/services/assistant_contracts.py`
- `backend/src/services/discovery_contracts.py`

If added, `services/schemas.py` should re-export or import those models so existing API imports remain stable during migration.

Do not create a new graph package hierarchy unless implementation evidence shows the current files are too large to safely modify.

## 13. Implementation Contracts

These are target contracts for the implementation plan. Exact names may be adjusted to match local style, but the semantics should remain stable.

### 13.1 Result Contracts

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
```

```python
class DiscoveryResult(BaseModel):
    enabled: bool
    top_k: list[dict] = Field(default_factory=list)
    rewritten_queries: list[str] = Field(default_factory=list)
    total_raw: int = 0
    total_deduped: int = 0
    scoring_summary: dict = Field(default_factory=dict)
    error: str | None = None
```

```python
class KnowledgeResult(BaseModel):
    enabled: bool
    answer: str | None = None
    sources: list[KnowledgeAnswerSource] = Field(default_factory=list)
    mode: str | None = None
    error: str | None = None
```

```python
class IdeaResult(BaseModel):
    enabled: bool
    ideas: list[IdeaOption] = Field(default_factory=list)
    supporting_evidence: list[IdeaSupportingEvidence] = Field(default_factory=list)
    log_id: int | None = None
    error: str | None = None
```

### 13.2 next_action Contract

```python
class NextActionOption(BaseModel):
    id: str
    label: str
    request_patch: dict = Field(default_factory=dict)
```

```python
class ResearchAssistantNextAction(BaseModel):
    type: Literal[
        "choose_path",
        "upload_pdf",
        "select_idea",
        "none",
    ]
    options: list[NextActionOption] = Field(default_factory=list)
    message: str | None = None
```

During compatibility migration, string options may still be accepted at the service boundary and normalized into structured options.

### 13.3 Node Contract

Main graph nodes should follow this shape:

```python
def node_name(state: dict) -> dict:
    return {
        "field_to_update": value,
        "errors": state["errors"] + new_errors,
    }
```

Rules:

- Nodes return partial state updates only.
- Route nodes update `route`, `mode`, and `route_reason`; they do not execute services.
- Execution nodes update one or more result summaries plus `assistant_message`, `next_action`, and `errors`.
- Subgraph invocation must receive the main graph memory snapshot:

```python
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
```

### 13.4 Discovery Result Mapping

The main graph should map subgraph output to `DiscoveryResult` at the boundary:

```python
DiscoveryResult(
    enabled=True,
    top_k=result["ranked_candidates"][: state["top_k"]],
    rewritten_queries=result.get("rewritten_queries", []),
    total_raw=len(result.get("raw_results", [])),
    total_deduped=len(result.get("deduped_papers", [])),
    scoring_summary={
        "ranked_count": len(result.get("ranked_candidates", [])),
    },
    error=None,
)
```

The main graph may count subgraph internals while constructing the summary, but it must not use those internals for routing or business decisions.

## 14. Migration Phases

The implementation should be split into safe, testable phases.

### Phase 1: Contract Additions Without Behavior Change

Goal:

- Add new Pydantic contracts and helper mapping functions.
- Preserve existing API response shape.

Allowed changes:

- Add `AssistantStageError`, `DiscoveryResult`, `KnowledgeResult`, `IdeaResult`, and structured next-action option types.
- Add conversion helpers from current `ResearchDiscoverySection` and `ResearchKnowledgeSection`.
- Add tests for model validation and compatibility mapping.

Not allowed:

- Do not change route behavior.
- Do not remove `discovery`, `knowledge`, or `ideas` fields yet.

### Phase 2: Error Model Upgrade

Goal:

- Move from broad `section` errors to stage-level recoverable errors.

Allowed changes:

- Update graph nodes to emit `stage/message/recoverable`.
- Keep response compatibility if old tests or UI still expect broad fields, either by temporary aliasing or by updating tests in the same PR.

Not allowed:

- Do not change discovery ranking or QA behavior.

### Phase 3: Routing Semantics Fix

Goal:

- Enforce current-request experiment log trigger semantics.

Allowed changes:

- Update `route_request`.
- Add tests proving stored memory logs do not trigger `research_idea`.
- Add future-safe support for `experiment_log_id` only if the persistence lookup is already available; otherwise document it as future schema.

Not allowed:

- Do not introduce session resume or checkpointing.

### Phase 4: Discovery Boundary Enforcement

Goal:

- Make the main graph consume `DiscoveryResult` summaries rather than raw subgraph internals.

Allowed changes:

- Add `_discovery_result_from_subgraph(...)` helper.
- Pass `state["memory_context"]` into discovery subgraph invocation.
- Keep intermediate discovery state inside `PaperDiscoveryState`.

Not allowed:

- Do not move pipeline order into a service.
- Do not introduce a full `DiscoveryService.run_pipeline()`.

### Phase 5: advanced_ready Grounded Answer

Goal:

- Convert `advanced_ready` from a guidance-only node into an answer-and-guide node.

Allowed changes:

- Call Knowledge QA.
- Return grounded answer when sources exist.
- Return explicit no-source fallback when sources do not exist.
- Return structured `next_action`.

Not allowed:

- Do not generate ungrounded answers.

### Phase 6: Response Shape Migration

Goal:

- Move public assistant response toward `discovery_result`, `knowledge_result`, and `idea_result`.

Allowed changes:

- Add new fields.
- Keep old fields as aliases for one migration window if the frontend still depends on them.
- Update frontend only if the API change requires it.

Not allowed:

- Do not break `/research/query`.
- Do not remove old fields before tests and frontend usage are updated.

### Phase 7: Final Verification And Trace Hygiene

Goal:

- Prove the refactor preserved current behavior while adding the new boundaries.

Required checks:

- Backend assistant workflow tests.
- Discovery graph tests.
- API smoke tests for `/research/assistant`.
- Offline MVP smoke if route-level behavior changes.
- `git diff --check`.

## 15. Execution Constraints

Implementation must follow these constraints:

- No behavior change in Phase 1 except accepting new typed contracts.
- Subgraph must remain runnable after every phase.
- `/research/assistant` must return a structurally valid response after every phase.
- `/research/query` must remain backward compatible.
- Routing must stay deterministic.
- Services must remain stateless with respect to graph routing.
- Discovery pipeline order must remain owned by the subgraph.
- Old stored logs must not automatically trigger `research_idea`.
- LLM failures must be recoverable where possible.
- Public response schema changes must be covered by tests before frontend changes.

## 16. PR-Sized Task Checklist

The implementation plan should split work into these PR-sized units:

1. Add assistant result and error contracts with compatibility tests.
2. Upgrade internal errors to stage-level recoverable errors.
3. Fix routing semantics for current-request experiment logs.
4. Add discovery boundary helper and pass memory snapshot into subgraph.
5. Convert `advanced_ready` to grounded QA plus next-action.
6. Migrate assistant response fields toward result summaries.
7. Clean up service ownership so no service owns the full discovery pipeline.
8. Run full verification and update docs if behavior changed.

## 17. Non-Goals

V1 does not implement:

- session resume
- LangGraph checkpoint
- interrupt-based multi-turn workflow
- autonomous planning
- automatic use of old logs as idea triggers
- automatic persistence of discovery candidates
- ungrounded QA generation
- full frontend redesign

## 18. Interview Narrative

Use this framing:

```text
This project uses LangGraph as a thin but explicit workflow orchestration layer.
The main graph owns deterministic routing and result aggregation. Discovery is
delegated to a subgraph-owned pipeline, while each computational step remains
inside focused services. State is treated as a structured feature store rather
than a transcript log, and LLM calls are constrained to query rewriting,
feature enrichment, grounded generation, and idea generation.
```

Avoid this framing:

```text
The system is a fully autonomous research agent that plans and controls itself.
```

That would overstate the current architecture and blur the explicit control boundaries that make this system explainable.
