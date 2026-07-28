# Research Routing Signal Design

## Status

Approved direction for the Wave 5 Task 7 correction. This design is intentionally narrower than a general tool-routing guard.

## Problem

The deterministic Leader needs a reliable answer to one bounded question: does the current request explicitly allow, explicitly deny, ambiguously conflict about, or not mention fresh research retrieval?

The current keyword and regular-expression approach mixes clause parsing with Leader plan selection. Repeatedly extending those expressions has produced false positives, false negatives, and incorrect negation scope.

## Boundary

`ResearchRoutingSignal` is a private input to `DeterministicLeaderPlanner`. It is not a complete planner and does not decide which Agent Team members execute.

It may only:

- normalize Unicode text;
- split the request into bounded clauses;
- classify explicit research retrieval permission or prohibition per clause;
- combine clause results conservatively;
- request clarification for conflicts or low-confidence retrieval intent.

It must not:

- create or validate `LeaderPlan` steps;
- choose Idea, Knowledge, or other Agent actions;
- dispatch Agent Team members;
- introduce web, file, tool, scope, or provider permission fields;
- replace `PlanValidator` or workflow orchestration.

A general `ToolRoutingSignal` with web/file/tool semantics requires a separate future spec and consumption path.

## Contract

```python
class ResearchRoutingSignal(BaseModel):
    decision: Literal["allow", "deny", "review_existing", "conflict", "none"]
    needs_clarify: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
```

The signal remains private to the deterministic planner. No API, persistence, or frontend schema changes are introduced.

## Clause Analysis

1. Normalize with Unicode NFKC and normalize curly apostrophes before tokenization.
2. Split on sentence punctuation and semicolons; split on `but`, `however`, or `yet`; split on `and` only when its right-hand side begins another retrieval request or retrieval negation. Other uses of `and` remain inside the clause.
3. Evaluate negation only inside its clause. A negation in one clause must not leak into another clause.
4. Recognize fresh retrieval only when a bounded request expression is associated with an academic retrieval target.
5. Recognize `review existing literature`, `review my papers`, `review experiment logs`, `review notes`, and equivalent saved/current research-material expressions as `review_existing`.
6. Treat bare `review` plus an academic target as ambiguous unless the same clause contains an explicit fresh-retrieval expression. Verbs such as `find`, `search`, `discover`, `recommend`, `show`, and `look for` retain the bounded eight-token academic-target rule. Marker phrases `latest`, `recent`, or `new` apply only to literature-collection targets (`paper(s)`, `literature`, `study/studies`, `article(s)`) and may contain at most two documented count or relevance modifiers before the target.
7. Unrelated language remains `none`; the parser does not contain branches for code, functions, text, files, or other general-assistant domains.

Clause results combine as follows:

- one or more `allow` clauses and no `deny` clauses -> `allow`;
- one or more `deny` clauses and no `allow` clauses -> `deny`;
- `review_existing` clauses without fresh retrieval -> `review_existing`;
- explicit fresh retrieval in the same review request -> `allow`;
- `deny` of fresh retrieval combined with `review_existing` -> `review_existing`;
- both `allow` and `deny` clauses -> `conflict`, `needs_clarify=True`;
- no retrieval clauses -> `none`, `needs_clarify=False`;
- ambiguous retrieval language below the `0.75` confidence threshold -> `conflict`, `needs_clarify=True`.

Exact bounded matches use confidence `1.0`. A confident absence of retrieval intent also uses `1.0`. Ambiguous retrieval language uses at most `0.5`; the value is diagnostic and does not independently select a plan.

The parser does not infer scope exceptions. For example, "do not search old literature, but find recent papers" is a conflict because scope constraints are outside this Wave 5 contract.

## Leader Integration

The Leader combines the signal with existing semantic inputs:

- `allow` permits `research` or, when Idea intent and an experiment log are present, `research_then_idea`.
- `deny` prevents `research` and `research_then_idea`.
- `review_existing` maps to `knowledge_qa` only when current saved-knowledge coverage is available; otherwise the Leader clarifies which existing research material should be reviewed.
- `conflict` produces a bounded clarification plan with no professional Agent steps.
- `none` leaves existing product, knowledge, Idea, and fallback routing unchanged.

Idea remains outside the parser. Idea routing depends on Idea intent, `experiment_log`, and current knowledge coverage. If an Idea request lacks sufficient knowledge while research is explicitly denied, the Leader clarifies instead of silently running Research.

`review_existing` is a research-domain routing signal, not a call to the fresh-discovery Research Agent. Under the frozen Agent ownership contract, saved-paper and confirmed-memory review uses `knowledge_qa`. Experiment-log or note review is recognized, but when no supported knowledge consumer is available the Leader clarifies rather than claiming an unsupported execution path.

The resulting `LeaderPlan` still passes through `PlanValidator`. Multi-Agent execution remains the responsibility of the workflow and dispatcher.

## Error Handling

The parser is deterministic and performs no I/O. Unsupported or ambiguous language must fail closed to `conflict` only when retrieval intent is present. Unrelated ordinary requests return `none`; they are not converted into parser-level clarification.

## Verification

Tests must cover:

- Unicode apostrophe normalization;
- clause-local negation;
- allow-only, deny-only, parallel allow, and allow/deny conflict;
- contrast and conjunction boundaries;
- explicit fresh academic retrieval with counts and modifiers;
- non-academic paper compounds;
- review of existing literature, saved papers, experiment logs, and notes;
- bare academic review returning low-confidence conflict;
- review combined with explicit fresh-search language returning allow;
- unrelated requests returning `none` without domain-specific branches;
- Idea intent remaining outside the parser;
- Leader integration for `allow`, `deny`, `review_existing`, `conflict`, and `none`;
- all existing eight reviewed few-shot decisions;
- full backend regression and `git diff --check`.

## Non-Goals

- General web or file search permissions.
- Tool selection or tool-call policy.
- Retrieval scope constraints.
- Agent dispatch or workflow orchestration.
- Dynamic Agents, loops, or autonomous planning.
