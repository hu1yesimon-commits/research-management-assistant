# Research Routing Signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the brittle Research keyword routing in the deterministic Leader with a private, clause-aware `ResearchRoutingSignal` that conservatively handles permission, prohibition, conflicts, and unrelated requests.

**Architecture:** A focused `agent_team/research_routing.py` module owns Unicode normalization, bounded clause splitting, clause-local retrieval classification, and signal aggregation. `DeterministicLeaderPlanner` consumes the signal but remains responsible for Idea, Knowledge, clarification, and typed plan selection; `PlanValidator` and workflow dispatch remain unchanged.

**Tech Stack:** Python 3.12, Pydantic v2, pytest.

---

## Scope And Stop Conditions

- Do not add web, file, tool, scope, provider, persistence, API, or frontend fields.
- Do not move Idea, Knowledge, Plan validation, or Agent dispatch into the parser.
- Do not modify allowed Plan types, Agent names, Actions, or dependencies.
- Stop if a requested behavior requires general tool policy or retrieval scope semantics.

## File Map

- Create `backend/src/agent_team/research_routing.py`: private signal and deterministic parser.
- Create `backend/src/tests/test_research_routing.py`: parser unit contract.
- Modify `backend/src/agent_team/planner.py`: consume the signal and remove the old parser.
- Modify `backend/src/tests/test_leader_planner.py`: Leader integration and frozen few-shot regressions.

### Task 1: Implement The Private Clause-Level Signal

**Files:**
- Create: `backend/src/agent_team/research_routing.py`
- Create: `backend/src/tests/test_research_routing.py`

- [ ] **Step 1: Write the failing signal and normalization tests**

Add tests for the exact contract and Unicode normalization:

```python
def test_signal_contract_is_private_and_bounded():
    signal = ResearchRoutingSignal(
        decision="allow", needs_clarify=False, confidence=1.0
    )
    assert signal.model_dump() == {
        "decision": "allow",
        "needs_clarify": False,
        "confidence": 1.0,
    }


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("I don't need papers", "deny"),
        ("I don’t need papers", "deny"),
        ("I do not need papers", "deny"),
    ],
)
def test_unicode_apostrophes_share_the_same_negation_semantics(message, expected):
    assert ResearchRoutingParser().parse(message).decision == expected
```

- [ ] **Step 2: Write failing clause, conflict, and ordinary-request tests**

Cover the frozen aggregation rules:

```python
@pytest.mark.parametrize(
    ("message", "decision", "needs_clarify"),
    [
        ("Find recent papers about graph reconstruction", "allow", False),
        ("Do not search for papers about graph reconstruction", "deny", False),
        ("Do not search literature; find recent papers", "conflict", True),
        ("Find papers and search recent literature", "allow", False),
        ("Do not find papers and do not search literature", "deny", False),
        ("Explain this function", "none", False),
        ("Rewrite this paragraph", "none", False),
        ("Read this code and explain the bug", "none", False),
    ],
)
def test_clause_level_decisions(message, decision, needs_clarify):
    signal = ResearchRoutingParser().parse(message)
    assert signal.decision == decision
    assert signal.needs_clarify is needs_clarify
```

Add one low-confidence retrieval-like case:

```python
def test_ambiguous_retrieval_language_requests_clarification():
    signal = ResearchRoutingParser().parse(
        "Help me with papers about graph reconstruction"
    )
    assert signal.decision == "conflict"
    assert signal.needs_clarify is True
    assert signal.confidence <= 0.5
```

Also retain the established collision cases:

```python
@pytest.mark.parametrize(
    ("message", "decision"),
    [
        ("Recommend three relevant papers about graph reconstruction", "allow"),
        ("Show me papers about graph reconstruction", "allow"),
        ("I need literature on graph reconstruction", "allow"),
        ("Find papers about creating new agent architectures", "allow"),
        ("Search for ideal graph reconstruction methods", "allow"),
        ("I need paper towels", "none"),
    ],
)
def test_bounded_retrieval_phrases_avoid_known_collisions(message, decision):
    assert ResearchRoutingParser().parse(message).decision == decision
```

- [ ] **Step 3: Run the parser tests to verify RED**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_routing.py -q
```

Expected: FAIL because `agent_team.research_routing` does not exist.

- [ ] **Step 4: Implement the bounded signal and parser**

Create these public types only:

```python
from typing import Literal

from pydantic import BaseModel, Field


class ResearchRoutingSignal(BaseModel):
    decision: Literal["allow", "deny", "conflict", "none"]
    needs_clarify: bool = False
    confidence: float = Field(ge=0.0, le=1.0)


class ResearchRoutingParser:
    def parse(self, message: str) -> ResearchRoutingSignal:
        """Return a private retrieval-routing guard signal."""
```

Implementation requirements:

- normalize using `unicodedata.normalize("NFKC", message)` and replace `’`/`‘` with `'`;
- normalize `don't` to `do not` before tokenization;
- split on `.`, `?`, `!`, `;`, `but`, `however`, and `yet`;
- split on `and` only when the right side begins a bounded retrieval request or retrieval negation;
- classify a clause as `allow` only when a request verb or `look for` is associated within eight tokens with `paper(s)`, `literature`, `study/studies`, `article(s)`, `evidence`, or `method(s)`;
- allow count and relevance modifiers between request and target;
- classify the same bounded expression as `deny` when `no`, `not`, `never`, or normalized `do not` occurs in that clause's request span;
- treat non-academic `paper towel(s)`, `paper plate(s)`, `paper bag(s)`, and `paper cup(s)` as no target;
- aggregate allow-only, deny-only, conflict, and none exactly as the design specifies;
- use confidence `1.0` for exact allow, deny, conflict, and confident none matches;
- treat `help` and `want` as ambiguous request cues rather than retrieval permission verbs; when one occurs within eight tokens of an academic target without an exact allow or deny expression, use `conflict`, `needs_clarify=True`, and confidence at most `0.5`.

Keep tokenization, clause splitting, clause classification, and aggregation in separate private methods. Do not return clauses or tool-policy fields.

- [ ] **Step 5: Run parser tests to verify GREEN**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_research_routing.py -q
```

Expected: PASS for Unicode, clause scope, allow, deny, conflict, ordinary none, and collision cases.

- [ ] **Step 6: Commit the parser**

```bash
git add backend/src/agent_team/research_routing.py backend/src/tests/test_research_routing.py
git commit -m "refactor: add bounded research routing signal"
```

### Task 2: Integrate The Signal Into The Deterministic Leader

**Files:**
- Modify: `backend/src/agent_team/planner.py`
- Modify: `backend/src/tests/test_leader_planner.py`

- [ ] **Step 1: Write failing Leader integration tests**

Add integration tests proving the parser is a guard rather than a planner:

```python
def make_plan(message, *, experiment_log=None, has_knowledge=False):
    return DeterministicLeaderPlanner().plan(
        PlannerInput(
            message=message,
            context=SessionContext(session_id="default"),
            experiment_log=experiment_log,
            has_knowledge=has_knowledge,
        )
    )


def test_conflicting_research_clauses_produce_clarification():
    plan = make_plan("Do not search literature; find recent papers")
    assert plan.plan_type == "clarify"
    assert plan.steps == []


def test_explicit_research_denial_blocks_research_then_idea(experiment_log):
    plan = make_plan(
        "Do not search for papers; propose an idea for this experiment",
        experiment_log=experiment_log,
        has_knowledge=False,
    )
    assert plan.plan_type == "clarify"
    assert plan.steps == []


def test_explicit_research_denial_still_allows_idea_with_coverage(experiment_log):
    plan = make_plan(
        "Do not search for papers; propose an idea for this experiment",
        experiment_log=experiment_log,
        has_knowledge=True,
    )
    assert plan.plan_type == "idea"


@pytest.mark.parametrize(
    "message",
    ["Explain this function", "Rewrite this paragraph", "Read this code"],
)
def test_non_retrieval_requests_do_not_become_parser_clarifications(message):
    signal = ResearchRoutingParser().parse(message)
    assert signal.decision == "none"
    assert signal.needs_clarify is False
```

Retain all eight reviewed few-shot tests and validate every generated plan with `PlanValidator`.

- [ ] **Step 2: Run the integration tests to verify RED**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_leader_planner.py -q
```

Expected: FAIL because the Leader still consumes the old boolean parser and cannot represent deny/conflict.

- [ ] **Step 3: Replace the old parser consumption**

In `DeterministicLeaderPlanner.plan()`:

```python
research_signal = ResearchRoutingParser().parse(message)
asks_for_ideas = self._contains_term(
    normalized,
    ("idea", "ideas", "propose", "next test", "direction"),
)

if research_signal.needs_clarify or research_signal.decision == "conflict":
    return _bounded_plan(
        "clarify",
        message,
        "Your request both allows and restricts fresh paper retrieval. Should the team search for new evidence?",
    )

research_allowed = research_signal.decision == "allow"
research_denied = research_signal.decision == "deny"
```

Apply these rules before existing plan selection:

- `research_allowed` plus Idea intent and experiment log -> `research_then_idea`;
- `research_allowed` without Idea intent -> `research`;
- Idea intent plus sufficient current knowledge -> `idea`, even when Research is denied;
- Idea intent without sufficient knowledge and with Research denied -> `clarify` with no steps;
- `none` leaves product, Knowledge, Idea, agent-creation, improve, and fallback behavior unchanged.

Delete the old `ResearchIntentParser` from `planner.py`. Do not move Idea detection or typed plan creation into `research_routing.py`.

- [ ] **Step 4: Run focused integration and validator tests**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest \
  backend/src/tests/test_research_routing.py \
  backend/src/tests/test_leader_planner.py \
  backend/src/tests/test_agent_plan_validator.py -q
```

Expected: PASS; exact eight few-shot decisions and all generated plan dependencies remain validator-valid.

- [ ] **Step 5: Run full backend verification**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
git diff --check
```

Expected: all backend tests PASS with no network access and `git diff --check` exits 0.

- [ ] **Step 6: Commit Leader integration**

```bash
git add backend/src/agent_team/planner.py backend/src/tests/test_leader_planner.py
git commit -m "fix: integrate bounded research routing signal"
```

### Task 3: Review And Wave 5 Handoff

**Files:**
- Modify: `docs/superpowers/plans/2026-06-30-agent-team-v3-implementation.md`

- [ ] **Step 1: Run independent spec review**

Verify the implementation line by line against `docs/superpowers/specs/2026-07-03-research-routing-signal-design.md`, including the private boundary and non-goals.

- [ ] **Step 2: Run independent code-quality review**

Audit Unicode normalization, clause boundaries, negation scope, conflict aggregation, ordinary `none` behavior, Leader integration, and regression coverage. Blocking or important findings require focused RED/GREEN fixes and re-review.

- [ ] **Step 3: Run final independent verification**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
git diff --check
git status --short
```

Expected: all backend tests PASS; diff check clean; only the append-only Wave 5 Execution Log is uncommitted.

- [ ] **Step 4: Append the Wave 5 Execution Log**

Record Task 7 and routing-correction commits, exact test counts, review results, the private Research-only signal boundary, known resolved findings, and `Wave 6 / Task 8` as the next unblocked wave.

- [ ] **Step 5: Commit the handoff**

```bash
git add docs/superpowers/plans/2026-06-30-agent-team-v3-implementation.md
git commit -m "docs: record agent team v3 wave 5 handoff"
```
