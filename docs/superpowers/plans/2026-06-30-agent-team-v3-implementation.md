# Agent Team V3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a default permanent research session with expiring per-turn paper candidates, bounded Leader planning, synchronous persistent Research/Idea agents, context summaries, and a session-first Vue workbench.

**Architecture:** Converge the completed Agent V1 worktree into the current assistant-first branch, then add a migration-backed `SessionStore` and transactional `CandidateLifecycleService`. A bounded Leader emits typed plans validated before a direct synchronous dispatcher invokes Knowledge QA, Research, or Idea adapters; `ConversationService` owns turn orchestration, persistence, partial failure, and summary refresh.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite, LangGraph, LangChain `ChatOpenAI`, pytest, Vue 3, Vitest, Vite.

---

## Scope And Execution Rules

- Execute in an isolated worktree created with `superpowers:using-git-worktrees` from the commit containing this plan.
- Recommended branch: `codex/agent-team-v3`.
- Keep `/research/assistant`, `/research/query`, and the legacy paper endpoints working during migration.
- Do not implement multi-session UI, SQLite Mailbox, resident workers, streaming, free ReAct loops, or dynamic agent creation.
- Use fake/deterministic providers in automated tests. Real provider checks are manual smoke tests only.
- Run a spec review and a code-quality review after Tasks 1, 5, 10, and 14.

## Model Assignment Strategy

This plan uses full `gpt-5.4` for bounded implementation work and `gpt-5.5` for ambiguity-heavy integration, state invariants, orchestration, and final review. This follows Codex guidance that GPT-5.5 is the starting point for demanding multi-step agents, while GPT-5.4 remains a strong coding, reasoning, and tool-use model.

Official references:

- `https://developers.openai.com/codex/models`
- `https://developers.openai.com/codex/concepts/subagents`

| Wave | Owner | Tasks | Gate before continuing |
|---|---|---|---|
| 1 | `gpt-5.5` high | Task 1 | Converged V1 baseline passes all tests and smoke |
| 2 | `gpt-5.4` medium | Task 2 | Migration tests and legacy store tests pass |
| 3 | `gpt-5.5` high | Tasks 3-4 | Turn and Candidate transactional invariants pass |
| 4 | `gpt-5.4` medium | Tasks 5-6 | Context and typed-plan tests pass; no architecture changes |
| 5 | `gpt-5.5` high | Task 7 | Leader planning and real-provider boundaries pass review |
| 6 | `gpt-5.4` medium | Task 8 | Agent adapters conform exactly to frozen ownership contracts |
| 7 | `gpt-5.5` high | Tasks 9-10 | Dispatcher and ConversationService failure semantics pass |
| 8 | `gpt-5.4` medium | Tasks 11-14 | API, frontend, Eval, build, and offline smoke pass |
| 9 | `gpt-5.5` high | Task 15 | Final architecture and verification review passes |

Do not run write-heavy waves in parallel. Both model conversations must use the same V3 worktree and branch, and each wave starts from the clean commit produced by the previous wave.

### GPT-5.4 Stop Conditions

GPT-5.4 must stop and hand control to GPT-5.5 when any of these occurs:

- The frozen spec and current code imply different state transitions.
- A task requires changing an Agent ownership boundary or allowed Plan type.
- Transaction, concurrency, idempotency, timeout, or partial-failure semantics are ambiguous.
- A prerequisite Task is incomplete or its verification is not green.
- The implementation would require expanding into Mailbox, multi-Session UI, streaming, or free-loop behavior.

GPT-5.4 may fix ordinary test failures within the assigned task when the expected contract is explicit.

### Model Handoff Record

At the end of every wave, append a short entry to the plan's `Execution Log` containing:

```text
Wave:
Owner model:
Completed task commits:
Current worktree and branch:
Verification commands and results:
Contract decisions made:
Known failures or blockers:
Next unblocked wave:
```

The receiving model must inspect `git status`, the listed commits, and the recorded verification before spawning implementation subagents.

### Copy-Safe GPT-5.4 Instruction

```text
在现有 Agent Team V3 worktree 中，按 docs/superpowers/plans/2026-06-30-agent-team-v3-implementation.md 使用 subagent-driven-development + TDD 执行当前已解锁且 Owner Model 为 gpt-5.4 的波次。每个 Task 使用 fresh subagent，并依次做规格复核和代码质量复核。开始前核对上一波 commit、git status 和验证记录；不得跳过依赖，不得修改冻结架构、Agent ownership、Plan 类型或状态机语义。完成当前连续可执行的 gpt-5.4 波次后，运行计划要求的验证，提交改动，填写 Execution Log，然后在下一个 gpt-5.5 波次前停止。
```

### Copy-Safe GPT-5.5 Instruction

```text
在现有 Agent Team V3 worktree 中，按 docs/superpowers/plans/2026-06-30-agent-team-v3-implementation.md 使用 subagent-driven-development + TDD 执行当前已解锁且 Owner Model 为 gpt-5.5 的波次。每个 Task 使用 fresh subagent，并依次做规格复核和代码质量复核。开始前核对上一波 commit、git status 和验证记录；重点验证分支收敛、事务原子性、Candidate/Session 状态机、Planner/Validator、Agent ownership、超时、幂等和部分失败语义。完成当前连续可执行的 gpt-5.5 波次后，运行计划要求的验证，提交改动，填写 Execution Log，然后在下一个 gpt-5.4 波次前停止。
```

## User Review Gates

- After Task 5, the user reviews Candidate expiration, refresh suppression, Session context, and Memory boundaries.
- During Task 7, the user owns the semantic review of the Leader few-shot decisions; implementation workers own provider wiring and tests.
- After Task 10, the user reviews plan types, Research/Idea ownership, partial-failure behavior, and the interview explanation.
- During Task 14, the user reviews the Planner Eval labels before the dataset is treated as the product truth source.
- Boilerplate migrations, CRUD, FastAPI wiring, Vue state plumbing, fixtures, and mechanical documentation updates can be executed by implementation workers.

## Target File Map

### Backend persistence and session boundary

- Create `backend/src/services/sqlite_migrations.py`: ordered SQLite migrations and default Session bootstrap.
- Create `backend/src/services/session_store.py`: Turns, Messages, Agent Contexts, Agent Runs, summary boundaries, and pagination.
- Create `backend/src/services/candidate_lifecycle.py`: Candidate Batch/Item state machine, refresh suppression, transactional Accept.
- Create `backend/src/services/session_context.py`: recent-turn context construction and rolling summary policy.
- Create `backend/src/services/session_schemas.py`: Session API and persistence-facing Pydantic contracts.
- Modify `backend/src/services/memory_store.py`: initialize migrations, SQLite pragmas, saved-paper filtering, accepted DOI deduplication.

### Backend Agent Team

- Create `backend/src/agent_team/__init__.py`: package marker.
- Create `backend/src/agent_team/contracts.py`: typed plans, tasks, results, and planner input.
- Create `backend/src/agent_team/validator.py`: deterministic plan-policy enforcement.
- Create `backend/src/agent_team/prompts.py`: Leader system prompt and few-shot cases.
- Create `backend/src/agent_team/planner.py`: deterministic and structured-LLM planners/responders.
- Create `backend/src/agent_team/research_agent.py`: Discovery Subgraph adapter and candidate freshness filtering.
- Create `backend/src/agent_team/idea_agent.py`: Idea Service adapter without internal discovery ownership.
- Create `backend/src/agent_team/dispatcher.py`: direct synchronous action dispatch.
- Create `backend/src/services/conversation_service.py`: transactional turn orchestration and partial-failure aggregation.
- Modify `backend/src/services/idea_service.py`: accept externally supplied research evidence while preserving the legacy endpoint.
- Modify `backend/src/config.py`: Leader and summary provider configuration.
- Modify `backend/src/main.py`: dependencies and Session/Saved Paper endpoints.

### Frontend

- Modify `frontend/src/api.js`: Session Turn, Message, Candidate, Accept, and Saved Paper clients.
- Create `frontend/src/components/SessionChatPanel.vue`: message history, composer, busy/error state.
- Create `frontend/src/components/AgentTracePanel.vue`: plan and Agent Run summaries.
- Create `frontend/src/components/ActiveCandidatesPanel.vue`: only current Session candidates and Accept actions.
- Modify `frontend/src/components/CandidateLifecyclePanel.vue`: present global saved-paper lifecycle, not recommendations.
- Modify `frontend/src/components/ResearchWorkbench.vue`: make the default Session the primary interaction surface.
- Modify `frontend/src/styles.css`: chat, trace, and active-candidate layout.

### Tests and verification

- Create `backend/src/tests/test_sqlite_migrations.py`.
- Create `backend/src/tests/test_session_store.py`.
- Create `backend/src/tests/test_candidate_lifecycle.py`.
- Create `backend/src/tests/test_session_context.py`.
- Create `backend/src/tests/test_agent_plan_validator.py`.
- Create `backend/src/tests/test_leader_planner.py`.
- Create `backend/src/tests/test_agent_dispatcher.py`.
- Create `backend/src/tests/test_conversation_service.py`.
- Create `backend/src/tests/test_session_api.py`.
- Create `backend/src/evals/leader_planner_cases.json`.
- Create `backend/src/tests/test_leader_planner_eval.py`.
- Create `frontend/src/components/__tests__/SessionChatPanel.test.js`.
- Create `frontend/src/components/__tests__/AgentTracePanel.test.js`.
- Create `frontend/src/components/__tests__/ActiveCandidatesPanel.test.js`.
- Modify `frontend/src/components/__tests__/ResearchWorkbench.test.js`.
- Modify `backend/scripts/smoke_offline_mvp.sh`.
- Create `docs/superpowers/reviews/2026-06-30-agent-team-v3-final-review.md`: GPT-5.5 final architecture and verification decision.

---

### Task 1: Converge Agent V1 And Assistant-First Frontend

**Owner Model:** `gpt-5.5`, reasoning `high`
**Prerequisite:** Plan commit is present; isolated V3 worktree is clean.
**Escalate/Stop:** Stop if conflicts extend beyond the listed integration surface or require changing the frozen V3 contract.

**Files:**
- Merge: branch `codex/agent-system-v1-refactor`
- Modify on conflict: `backend/src/tests/test_api_mvp.py`
- Modify on conflict: `frontend/src/components/AssistantWorkflowPanel.vue`
- Modify on conflict: `frontend/src/components/ResearchWorkbench.vue`
- Modify on conflict: `frontend/src/components/__tests__/AssistantWorkflowPanel.test.js`
- Modify on conflict: `frontend/src/components/__tests__/ResearchWorkbench.test.js`
- Modify: `frontend/src/components/AssistantSummaryPanel.vue`
- Test: `frontend/src/components/__tests__/AssistantSummaryPanel.test.js`

- [ ] **Step 1: Verify the isolated baseline before merging**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
cd frontend
npm test
npm run build
```

Expected: backend tests PASS, frontend tests PASS, and Vite build exits 0.

- [ ] **Step 2: Merge the completed V1 branch and inspect conflicts**

Run:

```bash
git merge --no-ff codex/agent-system-v1-refactor
git diff --name-only --diff-filter=U
```

Expected conflicts are limited to the backend API test and assistant/frontend files listed above. Stop if production backend files conflict unexpectedly and re-check the merge base before editing.

- [ ] **Step 3: Resolve the frontend contract intentionally**

Keep the current assistant-first page structure, memory summary, collapsed saved-paper lifecycle, and fallback query section. Bring across V1 typed backend results, stage errors, grounded-QA semantics, `failure` emission, and stale-result clearing. Do not duplicate Next Action, Ideas, or Workflow Notes inside both `AssistantWorkflowPanel` and `AssistantSummaryPanel`.

Use this rendering rule in `AssistantSummaryPanel.vue`:

```vue
<span
  v-for="option in summary.next_action.options"
  :key="option.id || option"
>
  option: {{ option.label || option }}
</span>

<strong>{{ workflowError.stage || workflowError.section || "workflow" }}:</strong>
```

Use this failure handler in `ResearchWorkbench.vue` while retaining `loadMemorySummary()`:

```js
function handleAssistantFailure() {
  assistantResponse.value = null;
  activeResultSource.value = "query";
}
```

- [ ] **Step 4: Add the conflict-resolution regression tests**

Add a structured-option case to `AssistantSummaryPanel.test.js`:

```js
test("renders structured next-action labels and stage errors", () => {
  const wrapper = mount(AssistantSummaryPanel, {
    props: {
      summary: {
        mode: "advanced",
        next_action: {
          type: "choose_path",
          message: "Choose the next workflow step.",
          options: [{ id: "continue_search", label: "Search papers", request_patch: {} }],
        },
        errors: [{ stage: "multi_search", message: "discovery unavailable" }],
      },
    },
  });

  expect(wrapper.text()).toContain("option: Search papers");
  expect(wrapper.text()).toContain("multi_search: discovery unavailable");
  expect(wrapper.text()).not.toContain("[object Object]");
});
```

- [ ] **Step 5: Verify the converged baseline**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
cd frontend
npm test
npm run build
cd ..
backend/scripts/smoke_offline_mvp.sh
git diff --check
```

Expected: all commands PASS and smoke prints `OFFLINE_MVP_SMOKE_OK=true`.

- [ ] **Step 6: Commit the baseline convergence**

```bash
git add backend frontend docs/superpowers/plans/2026-06-27-agent-system-v1-refactor-implementation.md
git commit -m "merge: converge agent v1 and assistant workbench"
```

---

### Task 2: Add Versioned SQLite Migrations And Default Session

**Owner Model:** `gpt-5.4`, reasoning `medium`
**Prerequisite:** Task 1 converged baseline is committed and green.
**Escalate/Stop:** Stop on any need to reinterpret existing user data or change Candidate/Session semantics.

**Files:**
- Create: `backend/src/services/sqlite_migrations.py`
- Modify: `backend/src/services/memory_store.py`
- Create: `backend/src/tests/test_sqlite_migrations.py`
- Modify: `backend/src/tests/test_memory_store.py`

- [x] **Step 1: Write failing migration tests**

```python
def test_migrations_create_default_session_and_v3_tables(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()

    with sqlite3.connect(store.database_path) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        default_session = connection.execute(
            "SELECT id, status FROM sessions WHERE id = 'default'"
        ).fetchone()

    assert {
        "schema_migrations",
        "sessions",
        "conversation_turns",
        "messages",
        "candidate_batches",
        "candidate_items",
        "agent_contexts",
        "agent_runs",
    } <= names
    assert default_session == ("default", "active")


def test_migrations_are_idempotent(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite3"))
    store.initialize()
    store.initialize()

    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE id = 'default'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 1"
        ).fetchone()[0] == 1
```

- [x] **Step 2: Run the tests to verify RED**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_sqlite_migrations.py -q
```

Expected: FAIL because the V3 tables do not exist.

- [x] **Step 3: Implement migration version 1**

Create `sqlite_migrations.py` with an ordered `MIGRATIONS` collection. Migration 1 must create every table and both partial unique indexes:

```python
MIGRATIONS = {
    1: """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        title TEXT,
        summary TEXT NOT NULL DEFAULT '',
        summary_through_message_id INTEGER,
        status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS conversation_turns (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id),
        idempotency_key TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
        plan_json TEXT,
        error_json TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT,
        UNIQUE(session_id, idempotency_key)
    );
    CREATE UNIQUE INDEX IF NOT EXISTS one_running_turn_per_session
        ON conversation_turns(session_id) WHERE status = 'running';
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL REFERENCES sessions(id),
        turn_id TEXT NOT NULL REFERENCES conversation_turns(id),
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'agent', 'system')),
        agent_name TEXT,
        content_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS messages_session_id_id
        ON messages(session_id, id);
    CREATE TABLE IF NOT EXISTS candidate_batches (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id),
        turn_id TEXT NOT NULL REFERENCES conversation_turns(id),
        query TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('active', 'expired')),
        created_at TEXT NOT NULL,
        expired_at TEXT
    );
    CREATE UNIQUE INDEX IF NOT EXISTS one_active_batch_per_session
        ON candidate_batches(session_id) WHERE status = 'active';
    CREATE TABLE IF NOT EXISTS candidate_items (
        id TEXT PRIMARY KEY,
        batch_id TEXT NOT NULL REFERENCES candidate_batches(id),
        paper_key TEXT NOT NULL,
        paper_snapshot_json TEXT NOT NULL,
        judgement_json TEXT,
        status TEXT NOT NULL CHECK (status IN ('active', 'accepted', 'expired')),
        accepted_paper_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(batch_id, paper_key)
    );
    CREATE TABLE IF NOT EXISTS agent_contexts (
        session_id TEXT NOT NULL REFERENCES sessions(id),
        agent_name TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        updated_through_message_id INTEGER,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(session_id, agent_name)
    );
    CREATE TABLE IF NOT EXISTS agent_runs (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id),
        turn_id TEXT NOT NULL REFERENCES conversation_turns(id),
        agent_name TEXT NOT NULL,
        action TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'skipped')),
        input_json TEXT NOT NULL,
        output_json TEXT,
        error_json TEXT,
        started_at TEXT NOT NULL,
        completed_at TEXT
    );
    """,
}
```

Implement `apply_migrations(database_path)` so it creates `schema_migrations`, applies missing versions in order, records each version, and inserts `default` with `INSERT OR IGNORE`. Use UTC ISO timestamps.

- [x] **Step 4: Wire migrations and SQLite pragmas**

At the end of `MemoryStore.initialize()`, call `apply_migrations(self.database_path)`. Change `_connect()` to:

```python
def _connect(self) -> sqlite3.Connection:
    connection = sqlite3.connect(self.database_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection
```

Set `PRAGMA journal_mode = WAL` once inside migration initialization, before beginning a migration transaction.

- [x] **Step 5: Run migration and legacy store tests**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_sqlite_migrations.py backend/src/tests/test_memory_store.py -q
```

Expected: PASS, including repeated initialization against an existing database.

- [x] **Step 6: Commit**

```bash
git add backend/src/services/sqlite_migrations.py backend/src/services/memory_store.py backend/src/tests/test_sqlite_migrations.py backend/src/tests/test_memory_store.py
git commit -m "feat: add versioned session migrations"
```

---

### Task 3: Implement Session Turn And Message Persistence

**Owner Model:** `gpt-5.5`, reasoning `high`
**Prerequisite:** Task 2 migration schema is committed and idempotent.
**Escalate/Stop:** Resolve transaction, concurrency, replay, and failure-state ambiguity here; do not defer it to API wiring.

**Files:**
- Create: `backend/src/services/session_schemas.py`
- Create: `backend/src/services/session_store.py`
- Create: `backend/src/tests/test_session_store.py`

- [x] **Step 1: Define session contracts and failing tests**

Add these contracts to `session_schemas.py`:

```python
class StartTurnResult(BaseModel):
    turn_id: str
    status: Literal["running", "completed", "failed"]
    replayed: bool = False


class StoredMessage(BaseModel):
    id: int
    session_id: str
    turn_id: str
    role: Literal["user", "assistant", "agent", "system"]
    agent_name: str | None = None
    content: dict
    created_at: str


class MessagePage(BaseModel):
    items: list[StoredMessage] = Field(default_factory=list)
    next_before_id: int | None = None
```

Write tests proving:

```python
def test_start_turn_saves_user_message_and_replays_idempotency(store):
    first = store.start_turn("default", "request-1", {"text": "find papers"})
    second = store.start_turn("default", "request-1", {"text": "find papers"})

    assert first.replayed is False
    assert second.replayed is True
    assert second.turn_id == first.turn_id
    assert [message.content["text"] for message in store.list_messages("default")] == ["find papers"]


def test_second_running_turn_is_rejected(store):
    store.start_turn("default", "request-1", {"text": "first"})

    with pytest.raises(SessionBusyError):
        store.start_turn("default", "request-2", {"text": "second"})
```

- [x] **Step 2: Run RED**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_session_store.py -q
```

Expected: FAIL because `SessionStore` does not exist.

- [x] **Step 3: Implement atomic turn start**

`SessionStore.start_turn()` must use `BEGIN IMMEDIATE` and perform operations in this order:

```python
connection.execute("BEGIN IMMEDIATE")
existing = connection.execute(
    "SELECT id, status FROM conversation_turns WHERE session_id = ? AND idempotency_key = ?",
    (session_id, idempotency_key),
).fetchone()
if existing is not None:
    connection.commit()
    return StartTurnResult(turn_id=existing["id"], status=existing["status"], replayed=True)

running = connection.execute(
    "SELECT id FROM conversation_turns WHERE session_id = ? AND status = 'running'",
    (session_id,),
).fetchone()
if running is not None:
    connection.rollback()
    raise SessionBusyError(session_id)

turn_id = str(uuid4())
now = self._now()
connection.execute(
    "INSERT INTO conversation_turns (id, session_id, idempotency_key, status, created_at) VALUES (?, ?, ?, 'running', ?)",
    (turn_id, session_id, idempotency_key, now),
)
connection.execute(
    "INSERT INTO messages (session_id, turn_id, role, content_json, created_at) VALUES (?, ?, 'user', ?, ?)",
    (session_id, turn_id, self._to_json(user_content), now),
)
connection.execute(
    "UPDATE candidate_items SET status = 'expired', updated_at = ? WHERE status = 'active' AND batch_id IN (SELECT id FROM candidate_batches WHERE session_id = ? AND status = 'active')",
    (now, session_id),
)
connection.execute(
    "UPDATE candidate_batches SET status = 'expired', expired_at = ? WHERE session_id = ? AND status = 'active'",
    (now, session_id),
)
connection.commit()
return StartTurnResult(turn_id=turn_id, status="running", replayed=False)
```

- [x] **Step 4: Implement completion, failure, pagination, and recent-turn reads**

Implement these public methods:

```python
complete_turn(turn_id, assistant_content, plan) -> None
fail_turn(turn_id, error) -> None
get_turn(session_id, turn_id) -> dict | None
get_replayed_response(session_id, turn_id) -> dict | None
list_messages(session_id, before_id=None, limit=50) -> list[StoredMessage]
list_recent_turn_messages(session_id, turn_limit=6) -> list[StoredMessage]
count_unsummarized_messages(session_id) -> int
update_session_summary(session_id, summary, through_message_id) -> None
get_agent_context(session_id, agent_name) -> str
upsert_agent_context(session_id, agent_name, summary, through_message_id) -> None
start_agent_run(session_id, turn_id, agent_name, action, input_data) -> str
finish_agent_run(run_id, status, output=None, error=None) -> None
```

`complete_turn()` must save the complete serialized `SessionTurnResponse` as the assistant message content before marking the Turn completed, so idempotent retries can return the original response.

Use this transaction shape for completion:

```python
def complete_turn(self, turn_id: str, assistant_content: dict, plan: dict) -> None:
    now = self._now()
    with self._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        turn = connection.execute(
            "SELECT session_id, status FROM conversation_turns WHERE id = ?",
            (turn_id,),
        ).fetchone()
        if turn is None:
            connection.rollback()
            raise TurnNotFoundError(turn_id)
        if turn["status"] != "running":
            connection.rollback()
            raise TurnStateError(turn_id, turn["status"])
        connection.execute(
            "INSERT INTO messages (session_id, turn_id, role, content_json, created_at) VALUES (?, ?, 'assistant', ?, ?)",
            (turn["session_id"], turn_id, self._to_json(assistant_content), now),
        )
        connection.execute(
            "UPDATE conversation_turns SET status = 'completed', plan_json = ?, completed_at = ? WHERE id = ?",
            (self._to_json(plan), now, turn_id),
        )
        connection.commit()
```

`list_messages()` must query `id < before_id` when a cursor is present, order by `id DESC` with `LIMIT`, then reverse the rows before returning them so each page renders chronologically. `list_recent_turn_messages()` must select the six newest completed Turn IDs and return their messages ordered by message ID.

- [x] **Step 5: Verify persistence behavior**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_session_store.py -q
```

Expected: PASS for idempotency, busy rejection, ordering, pagination, completion replay, and failure persistence.

- [x] **Step 6: Commit**

```bash
git add backend/src/services/session_schemas.py backend/src/services/session_store.py backend/src/tests/test_session_store.py
git commit -m "feat: persist session turns and messages"
```

---

### Task 4: Implement Candidate Lifecycle And Real Refresh Semantics

**Owner Model:** `gpt-5.5`, reasoning `high`
**Prerequisite:** Task 3 atomic Turn start and message persistence are green.
**Escalate/Stop:** Stop if Accept cannot remain atomic with Paper persistence or refresh needs a permanent blacklist.

**Files:**
- Create: `backend/src/services/candidate_lifecycle.py`
- Create: `backend/src/tests/test_candidate_lifecycle.py`
- Modify: `backend/src/services/memory_store.py`
- Modify: `backend/src/tests/test_memory_store.py`

- [x] **Step 1: Write failing Candidate state tests**

Cover all required transitions:

```python
def test_new_turn_expires_previous_unaccepted_candidates(session_store, candidate_service):
    first = session_store.start_turn("default", "turn-1", {"text": "first"})
    candidate_service.create_batch("default", first.turn_id, "first", [make_candidate("paper-1")])
    session_store.complete_turn(first.turn_id, {"assistant_message": "done"}, {"plan_type": "research"})

    session_store.start_turn("default", "turn-2", {"text": "second"})

    assert candidate_service.list_active("default") == []
    assert candidate_service.get_item_status("paper-1") == "expired"


def test_accept_is_transactional_and_idempotent(candidate_service, active_candidate):
    first = candidate_service.accept("default", active_candidate.id)
    second = candidate_service.accept("default", active_candidate.id)

    assert first.status == "accepted"
    assert second == first
    assert candidate_service.get_saved_paper(first.paper_id)["status"] == "accepted"


def test_expired_candidate_cannot_be_accepted(candidate_service, expired_candidate):
    with pytest.raises(CandidateExpiredError):
        candidate_service.accept("default", expired_candidate.id)
```

- [x] **Step 2: Run RED**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_candidate_lifecycle.py -q
```

Expected: FAIL because the lifecycle service is missing.

- [x] **Step 3: Implement stable paper keys and freshness filtering**

Use normalized DOI first, then `paper_id`:

```python
def paper_key(paper: dict) -> str:
    raw_doi = paper.get("doi") or (paper.get("source_ids") or {}).get("doi")
    if raw_doi:
        normalized = raw_doi.strip().lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break
        return f"doi:{normalized}"
    return f"paper:{paper['paper_id']}"
```

Implement:

```python
suppression_keys(session_id) -> set[str]
filter_fresh(session_id, ranked_candidates, top_k) -> list[dict]
create_batch(session_id, turn_id, query, candidates) -> CandidateBatch
list_active(session_id) -> list[SessionCandidate]
accept(session_id, candidate_id) -> CandidateAcceptResponse
```

Add these contracts to `session_schemas.py` before implementing the service:

```python
class SessionCandidate(BaseModel):
    id: str
    batch_id: str
    paper_key: str
    paper_snapshot: PaperMetadata
    judgement: JudgeResult | None = None
    status: Literal["active", "accepted", "expired"]


class CandidateBatch(BaseModel):
    id: str
    session_id: str
    turn_id: str
    query: str
    status: Literal["active", "expired"]
    candidates: list[SessionCandidate] = Field(default_factory=list)


class CandidateAcceptResponse(BaseModel):
    candidate_id: str
    paper_id: str
    status: Literal["accepted"] = "accepted"


class SavedPaper(BaseModel):
    paper_id: str
    title: str
    doi: str | None = None
    source: str
    authors: list[str] = Field(default_factory=list)
    status: Literal["accepted", "uploaded", "chunked", "embedded"]
    pdf_path: str | None = None
```

`suppression_keys()` must combine global Saved Papers in `accepted|uploaded|chunked|embedded` with the most recent expired Batch in the same Session. `filter_fresh()` must return fewer than `top_k` rather than refill with suppressed papers.

- [x] **Step 4: Implement transactional Accept**

Inside one `BEGIN IMMEDIATE` transaction:

1. Read Candidate Item joined to its Batch and Session.
2. Return the stored accepted result when status is already `accepted`.
3. Raise `CandidateExpiredError` when status is `expired`.
4. Deserialize `PaperMetadata` and optional `JudgeResult`.
5. Upsert `papers` with `status='accepted'` without downgrading `uploaded|chunked|embedded`.
6. Insert the judgement when present.
7. Mark Candidate Item `accepted` with `accepted_paper_id`.
8. Commit.

- [x] **Step 5: Fix saved-paper and DOI semantics**

Add `MemoryStore.list_saved_papers(limit=100)` filtering:

```sql
WHERE p.status IN ('accepted', 'uploaded', 'chunked', 'embedded')
```

Change `list_known_dois()` to use the same four statuses. Do not return legacy `papers.status='candidate'` from the new Saved Papers method.

- [x] **Step 6: Verify Candidate and paper behavior**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_candidate_lifecycle.py backend/src/tests/test_memory_store.py -q
```

Expected: PASS for expiration, suppression, under-filled fresh results, Accept idempotency, 409-domain error, and Saved Paper filtering.

- [x] **Step 7: Commit**

```bash
git add backend/src/services/candidate_lifecycle.py backend/src/services/memory_store.py backend/src/tests/test_candidate_lifecycle.py backend/src/tests/test_memory_store.py
git commit -m "feat: add session candidate lifecycle"
```

---

### Task 5: Add Context Windows And Rolling Session Summaries

**Owner Model:** `gpt-5.4`, reasoning `medium`
**Prerequisite:** Tasks 3-4 are committed; Session and Candidate state semantics are frozen.
**Escalate/Stop:** Stop if context construction would merge Session history, Agent Context, Confirmed Memory, or vector knowledge into one store.

**Files:**
- Create: `backend/src/services/session_context.py`
- Create: `backend/src/tests/test_session_context.py`
- Modify: `backend/src/services/session_schemas.py`

- [ ] **Step 1: Write failing context-window tests**

```python
def test_context_uses_summary_and_only_six_recent_turns(populated_store):
    context = SessionContextBuilder(populated_store).build("default")

    assert context.session_summary == "older research summary"
    assert len({message.turn_id for message in context.recent_messages}) == 6
    assert "turn-1" not in {message.turn_id for message in context.recent_messages}


def test_summary_refresh_runs_at_twelve_unsummarized_messages(populated_store):
    generator = FakeSummaryGenerator("new compact summary")
    service = SessionSummaryService(populated_store, generator, threshold=12)

    refreshed = service.maybe_refresh("default")

    assert refreshed is True
    assert populated_store.get_session("default")["summary"] == "new compact summary"
```

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_session_context.py -q
```

Expected: FAIL because context services do not exist.

- [ ] **Step 3: Implement the context contracts**

```python
class SessionContext(BaseModel):
    session_id: str
    session_summary: str = ""
    recent_messages: list[StoredMessage] = Field(default_factory=list)
    confirmed_memory: str = ""
    agent_contexts: dict[str, str] = Field(default_factory=dict)
    current_knowledge: list[KnowledgeSearchResult] = Field(default_factory=list)


class SummaryGenerator(Protocol):
    def summarize(self, previous_summary: str, messages: list[StoredMessage]) -> str:
        """Return a replacement rolling summary."""
```

Add `MemoryStore.build_confirmed_memory_context()` that formats only `semantic_memory.status='confirmed'`. `SessionContextBuilder.build()` must load the Session summary, six recent complete Turns, that confirmed-only memory text, and the three role contexts. `current_knowledge` starts empty and is filled by the current Turn's coverage probe; do not use `build_memory_context()` here because it also contains recent episodic logs.

- [ ] **Step 4: Implement summary refresh and a deterministic offline generator**

```python
class DeterministicSummaryGenerator:
    def summarize(self, previous_summary: str, messages: list[StoredMessage]) -> str:
        lines = [previous_summary.strip()] if previous_summary.strip() else []
        lines.extend(
            f"{message.role}: {str(message.content.get('text') or message.content.get('assistant_message') or '')[:400]}"
            for message in messages
        )
        return "\n".join(line for line in lines if line)[-6000:]
```

`SessionSummaryService.maybe_refresh()` returns `False` below 12 unsummarized messages. At or above the threshold it updates `summary` and `summary_through_message_id`; generator failure must leave the old summary unchanged and return `False`.

- [ ] **Step 5: Verify context isolation and failure tolerance**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_session_context.py -q
```

Expected: PASS for six-Turn limit, summary boundary, agent-specific context, threshold behavior, and non-fatal generator failure.

- [ ] **Step 6: Run the Phase 1-2 backend suite and review the spec boundary**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
git diff --check
```

Expected: PASS. Confirm Candidate is Session-scoped, Saved Papers are global, and Confirmed Memory remains review-gated.

- [ ] **Step 7: Commit**

```bash
git add backend/src/services/session_context.py backend/src/services/session_schemas.py backend/src/tests/test_session_context.py
git commit -m "feat: build bounded session context"
```

---

### Task 6: Define Typed Agent Plans And Deterministic Validation

**Owner Model:** `gpt-5.4`, reasoning `medium`
**Prerequisite:** Task 5 context contracts are committed.
**Escalate/Stop:** Do not add Plan types, Actions, dynamic Agents, loops, or persistence actions beyond the frozen allowlist.

**Files:**
- Create: `backend/src/agent_team/__init__.py`
- Create: `backend/src/agent_team/contracts.py`
- Create: `backend/src/agent_team/validator.py`
- Create: `backend/src/tests/test_agent_plan_validator.py`

- [ ] **Step 1: Write failing validator tests**

Test the six allowed plan types and all prohibited behavior:

```python
def test_research_then_idea_requires_exact_dependency(validator, experiment_log):
    plan = LeaderPlan(
        goal="find evidence and propose an idea",
        plan_type="research_then_idea",
        steps=[
            PlanStep(id="research-1", agent="research", action="recommend_papers", input={}),
            PlanStep(id="idea-1", agent="idea", action="generate_ideas", input={}, depends_on=[]),
        ],
    )

    with pytest.raises(PlanValidationError, match="depend on research-1"):
        validator.validate(plan, experiment_log=experiment_log)


def test_unknown_actions_are_rejected_by_schema():
    with pytest.raises(ValidationError):
        PlanStep(id="bad", agent="research", action="accept_paper", input={})
```

- [ ] **Step 2: Define exact plan contracts**

```python
PlanType = Literal[
    "direct_reply",
    "knowledge_qa",
    "research",
    "idea",
    "research_then_idea",
    "clarify",
]
AgentName = Literal["knowledge", "research", "idea"]
AgentAction = Literal["answer", "recommend_papers", "generate_ideas"]


class PlanStep(BaseModel):
    id: str = Field(min_length=1)
    agent: AgentName
    action: AgentAction
    input: dict = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class LeaderPlan(BaseModel):
    goal: str = Field(min_length=1)
    plan_type: PlanType
    steps: list[PlanStep] = Field(default_factory=list, max_length=2)
    needs_clarification: bool = False
    clarification_question: str | None = None
```

Also define these contracts:

```python
class PlannerInput(BaseModel):
    message: str
    context: SessionContext
    experiment_log: ExperimentLogRequest | None = None
    has_knowledge: bool = False


class ResearchResult(BaseModel):
    enabled: bool = True
    batch_id: str | None = None
    requested_top_k: int
    returned_count: int
    top_k: list[dict] = Field(default_factory=list)
    rewritten_queries: list[str] = Field(default_factory=list)
    total_raw: int = 0
    total_deduped: int = 0
    error: str | None = None


class AgentTask(BaseModel):
    step: PlanStep
    session_id: str
    turn_id: str


class AgentError(BaseModel):
    agent_name: Literal["leader", "knowledge", "research", "idea"]
    stage: str
    message: str
    recoverable: bool = True


class AgentResult(BaseModel):
    agent_name: Literal["knowledge", "research", "idea"]
    action: AgentAction
    status: Literal["completed", "failed", "skipped"]
    knowledge: KnowledgeResult | None = None
    research: ResearchResult | None = None
    idea: IdeaResult | None = None
    errors: list[AgentError] = Field(default_factory=list)


class AgentRunSummary(BaseModel):
    agent_name: str
    action: str
    status: Literal["completed", "failed", "skipped"]
```

- [ ] **Step 3: Implement exact policy validation**

Use a static map:

```python
EXPECTED_STEPS = {
    "direct_reply": [],
    "clarify": [],
    "knowledge_qa": [("knowledge", "answer")],
    "research": [("research", "recommend_papers")],
    "idea": [("idea", "generate_ideas")],
    "research_then_idea": [
        ("research", "recommend_papers"),
        ("idea", "generate_ideas"),
    ],
}
```

Validator rules:

- Step count and `(agent, action)` sequence must exactly match the plan type.
- Step IDs must be unique.
- `research_then_idea` step 2 must depend only on step 1.
- `idea` and `research_then_idea` require `experiment_log`.
- `clarify` requires a non-empty clarification question.
- Other plans must not set `needs_clarification`.

- [ ] **Step 4: Run GREEN**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_agent_plan_validator.py -q
```

Expected: PASS for valid plans, invalid sequences, unknown actions, missing evidence, duplicate IDs, and forbidden loops.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent_team backend/src/tests/test_agent_plan_validator.py
git commit -m "feat: define bounded agent plans"
```

---

### Task 7: Implement Leader Planning, Few-Shot Prompts, And Response Generation

**Owner Model:** `gpt-5.5`, reasoning `high`
**Prerequisite:** Task 6 typed schemas and Validator are green.
**Escalate/Stop:** Stop if prompting alone is being used as a hard guarantee or if provider wiring bypasses typed validation.

**Files:**
- Create: `backend/src/agent_team/prompts.py`
- Create: `backend/src/agent_team/planner.py`
- Create: `backend/src/tests/test_leader_planner.py`
- Modify: `backend/src/config.py`

- [ ] **Step 1: Write failing deterministic and structured-LLM planner tests**

```python
@pytest.mark.parametrize(
    ("message", "has_knowledge", "experiment_log", "expected"),
    [
        ("Find recent papers about graph reconstruction", False, None, "research"),
        ("Explain the saved evidence", True, None, "knowledge_qa"),
        ("Generate ideas from this experiment", True, make_log(), "idea"),
        ("Find recent papers and propose ideas", False, make_log(), "research_then_idea"),
    ],
)
def test_deterministic_planner_routes_bounded_cases(message, has_knowledge, experiment_log, expected):
    plan = DeterministicLeaderPlanner().plan(
        PlannerInput(
            message=message,
            context=SessionContext(session_id="default"),
            experiment_log=experiment_log,
            has_knowledge=has_knowledge,
        )
    )
    assert plan.plan_type == expected
```

For the LLM planner, inject a fake chat model and assert `with_structured_output(LeaderPlan)` is used and the rendered prompt includes the Session Summary but not unrelated full history.

- [ ] **Step 2: Add the Leader prompt and few-shot decisions**

`LEADER_SYSTEM_PROMPT` must state:

```text
You are the only user-facing research team leader.
Choose exactly one bounded plan type.
Use research only for fresh paper discovery.
Use idea when an experiment log exists and current knowledge is sufficient.
Use research_then_idea when fresh literature is required before idea generation.
Never accept papers, create agents, or invent actions.
Ask one clarification question when required input is missing.
```

Add this decision set to `FEW_SHOT_CASES`; the prompt builder serializes each input and validated plan as a user/assistant example pair:

```python
FEW_SHOT_CASES = [
    {
        "message": "Find recent papers about graph reconstruction",
        "has_knowledge": False,
        "has_experiment_log": False,
        "plan_type": "research",
    },
    {
        "message": "Explain what the saved papers say about oversmoothing",
        "has_knowledge": True,
        "has_experiment_log": False,
        "plan_type": "knowledge_qa",
    },
    {
        "message": "Use this experiment to propose the next small test",
        "has_knowledge": True,
        "has_experiment_log": True,
        "plan_type": "idea",
    },
    {
        "message": "Find newer evidence, then propose ideas for this experiment",
        "has_knowledge": False,
        "has_experiment_log": True,
        "plan_type": "research_then_idea",
    },
    {
        "message": "Improve it",
        "has_knowledge": False,
        "has_experiment_log": False,
        "plan_type": "clarify",
        "clarification_question": "Which experiment, paper, or metric do you want to improve?",
    },
    {
        "message": "What can this research workbench do?",
        "has_knowledge": False,
        "has_experiment_log": False,
        "plan_type": "direct_reply",
    },
    {
        "message": "Search papers and automatically accept every result",
        "has_knowledge": False,
        "has_experiment_log": False,
        "plan_type": "research",
    },
    {
        "message": "Create a statistics agent and let it decide",
        "has_knowledge": False,
        "has_experiment_log": False,
        "plan_type": "clarify",
        "clarification_question": "The team has fixed Leader, Research, and Idea roles. What research outcome should the existing team produce?",
    },
]
```

- [ ] **Step 3: Implement planner protocols and providers**

```python
class LeaderPlanner(Protocol):
    def plan(self, planner_input: PlannerInput) -> LeaderPlan:
        """Return one bounded typed plan."""


class LeaderResponder(Protocol):
    def respond(
        self,
        planner_input: PlannerInput,
        plan: LeaderPlan,
        results: list[AgentResult],
    ) -> str:
        """Return the Leader's final user-facing message."""
```

`StructuredLLMLeaderPlanner.plan()` must call:

```python
structured_model = self.chat_model.with_structured_output(LeaderPlan)
return structured_model.invoke(self.prompt_builder.messages(planner_input))
```

`DeterministicLeaderPlanner` is the offline default. `DeterministicLeaderResponder` must report completed results and errors without inventing evidence.

In `session_context.py`, also add the configured real summary implementation:

```python
class LLMSummaryGenerator:
    def __init__(self, chat_model):
        self.chat_model = chat_model

    def summarize(self, previous_summary: str, messages: list[StoredMessage]) -> str:
        transcript = "\n".join(
            f"{message.role}: {json.dumps(message.content, ensure_ascii=False)}"
            for message in messages
        )
        response = self.chat_model.invoke(
            [
                ("system", "Compress the research conversation into factual goals, decisions, evidence, and unresolved questions. Do not create long-term user memory."),
                ("user", f"Previous summary:\n{previous_summary}\n\nNew messages:\n{transcript}"),
            ]
        )
        return str(response.content).strip()
```

Add a fake-model test proving the previous summary and unsummarized messages are included and provider failure leaves the stored summary unchanged.

- [ ] **Step 4: Add configuration**

Add:

```python
leader_provider: str = "deterministic"
leader_model: str = "deepseek-chat"
leader_temperature: float = 0.0
summary_provider: str = "deterministic"
agent_step_timeout_seconds: float = 60.0
turn_timeout_seconds: float = 120.0
```

Map `LEADER_PROVIDER`, `LEADER_MODEL`, `LEADER_TEMPERATURE`, `SUMMARY_PROVIDER`, `AGENT_STEP_TIMEOUT_SECONDS`, and `TURN_TIMEOUT_SECONDS` environment variables. Permit `deterministic`, `openai`, and `deepseek` for Leader/Summary construction; reject unknown values in dependency construction.

- [ ] **Step 5: Run planner tests**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_leader_planner.py backend/src/tests/test_agent_plan_validator.py -q
```

Expected: PASS without network access.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agent_team/prompts.py backend/src/agent_team/planner.py backend/src/config.py backend/src/tests/test_leader_planner.py
git commit -m "feat: add bounded leader planner"
```

---

### Task 8: Implement Research And Idea Agent Adapters

**Owner Model:** `gpt-5.4`, reasoning `medium`
**Prerequisite:** Task 7 Planner contracts and provider boundaries are committed.
**Escalate/Stop:** Stop if Idea would own fresh Discovery, Research would auto-Accept, or an adapter needs to change the main architecture.

**Files:**
- Create: `backend/src/agent_team/research_agent.py`
- Create: `backend/src/agent_team/idea_agent.py`
- Modify: `backend/src/services/idea_service.py`
- Create: `backend/src/tests/test_agent_dispatcher.py`
- Modify: `backend/src/tests/test_idea_service.py`

- [ ] **Step 1: Write failing Research Agent tests**

```python
def test_research_agent_filters_saved_and_recent_expired_candidates(fake_graph, candidate_service):
    agent = ResearchAgent(fake_graph, candidate_service)

    result = agent.run(
        session_id="default",
        turn_id="turn-2",
        query="graph reconstruction",
        memory_context="session research context",
        top_k=5,
    )

    assert [item["paper"]["paper_id"] for item in result.research.top_k] == ["fresh-paper"]
    assert result.research.requested_top_k == 5
    assert result.research.returned_count == 1
```

- [ ] **Step 2: Implement ResearchAgent**

Invoke the V1 Discovery Subgraph with an authoritative snapshot:

```python
graph_result = self.discovery_graph.invoke(
    {
        "mode": "advanced",
        "user_query": query,
        "memory_context": memory_context,
        "memory_context_is_snapshot": True,
        "rewritten_queries": [],
        "raw_results": [],
        "normalized_papers": [],
        "deduped_papers": [],
        "judge_results": [],
        "judge_failures": [],
        "ranked_candidates": [],
    }
)
fresh = self.candidate_service.filter_fresh(
    session_id,
    graph_result.get("ranked_candidates", []),
    top_k,
)
batch = self.candidate_service.create_batch(session_id, turn_id, query, fresh) if fresh else None
```

Return typed counts, rewritten queries, judge failures, Candidate Batch ID, and the fresh top results. Catch only typed `DiscoveryStageError`; unknown programming errors must propagate.

- [ ] **Step 3: Write failing Idea Agent evidence tests**

```python
def test_idea_agent_uses_research_evidence_without_running_discovery(fake_idea_service, experiment_log):
    agent = IdeaAgent(fake_idea_service)
    research_candidates = [make_candidate("fresh-paper")]

    result = agent.run(
        experiment_log=experiment_log,
        research_candidates=research_candidates,
        idea_count=3,
    )

    assert fake_idea_service.received_candidates == research_candidates
    assert fake_idea_service.include_discovery is False
    assert result.idea.enabled is True
```

- [ ] **Step 4: Separate Idea generation from fresh discovery ownership**

Add `discovery_candidates: list[dict] | None = None` to `IdeaRecommendationService.recommend()`. Apply this precedence:

```python
candidates = list(discovery_candidates or [])
if discovery_candidates is None and include_discovery and self.discovery_graph is not None:
    candidates = self._legacy_discovery(query, top_k)
```

The new Idea Agent always passes a list and `include_discovery=False`. The legacy `/ideas/recommend` path keeps its current optional discovery behavior during compatibility migration.

- [ ] **Step 5: Verify adapters and legacy Idea behavior**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_agent_dispatcher.py backend/src/tests/test_idea_service.py backend/src/tests/test_paper_discovery_graph.py -q
```

Expected: PASS; Research alone creates Candidate Batch, Idea never creates one, and the legacy Idea endpoint still supports its flag.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agent_team/research_agent.py backend/src/agent_team/idea_agent.py backend/src/services/idea_service.py backend/src/tests/test_agent_dispatcher.py backend/src/tests/test_idea_service.py
git commit -m "feat: add research and idea agents"
```

---

### Task 9: Add The Direct Synchronous Dispatcher And Agent Run Persistence

**Owner Model:** `gpt-5.5`, reasoning `high`
**Prerequisite:** Task 8 adapters conform to the frozen Agent ownership boundary.
**Escalate/Stop:** Resolve dependency skipping, timeout, unexpected-exception, and Agent Run terminal-state semantics before continuing.

**Files:**
- Create: `backend/src/agent_team/dispatcher.py`
- Modify: `backend/src/tests/test_agent_dispatcher.py`
- Modify: `backend/src/services/session_store.py`

- [ ] **Step 1: Write failing dispatch and dependency tests**

```python
def test_research_then_idea_passes_research_output_to_idea(dispatcher, plan, experiment_log):
    results = dispatcher.execute(
        session_id="default",
        turn_id="turn-1",
        plan=plan,
        experiment_log=experiment_log,
        context=make_context(),
    )

    assert [result.agent_name for result in results] == ["research", "idea"]
    assert dispatcher.idea_agent.received_candidates == results[0].research.top_k


def test_failed_dependency_marks_idea_skipped(dispatcher_with_failing_research, plan, experiment_log):
    results = dispatcher_with_failing_research.execute(
        "default", "turn-1", plan, experiment_log, make_context()
    )

    assert results[0].status == "failed"
    assert results[1].status == "skipped"


def test_agent_step_timeout_becomes_typed_failure(timeout_dispatcher, research_plan):
    results = timeout_dispatcher.execute(
        "default", "turn-1", research_plan, None, make_context()
    )
    assert results[0].status == "failed"
    assert results[0].errors[0].stage == "timeout"
```

- [ ] **Step 2: Implement `AgentDispatcher` and `DirectAgentDispatcher`**

```python
class AgentDispatcher(Protocol):
    def execute(
        self,
        session_id: str,
        turn_id: str,
        plan: LeaderPlan,
        experiment_log: ExperimentLogRequest | None,
        context: SessionContext,
    ) -> list[AgentResult]:
        """Execute a validated bounded plan."""
```

Dispatch rules:

- `knowledge.answer` calls `KnowledgeQAService.answer()`.
- `research.recommend_papers` calls `ResearchAgent.run()`.
- `idea.generate_ideas` calls `IdeaAgent.run()` and receives Research output when declared as a dependency.
- Each step creates an `agent_runs` row before execution and completes it as `completed`, `failed`, or `skipped`.
- Typed service errors become recoverable `AgentError`; unexpected exceptions complete the run as failed and re-raise.
- Run each step through a `ThreadPoolExecutor` and call `future.result(timeout=agent_step_timeout_seconds)`. On timeout, mark the Run failed with stage `timeout`, call `executor.shutdown(wait=False, cancel_futures=True)`, and continue only when no later Step depends on it.

- [ ] **Step 3: Persist role-specific context after successful runs**

Update only the executing Agent's context. Use concise structured summaries:

```python
research_summary = f"query={query}; returned={returned_count}; accepted_saved_context={saved_count}"
idea_summary = f"experiment={experiment_log.task}; ideas={', '.join(idea.title for idea in ideas)}"
```

Do not copy the full Leader message history into Research or Idea context.

- [ ] **Step 4: Run dispatcher tests**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_agent_dispatcher.py backend/src/tests/test_session_store.py -q
```

Expected: PASS for single-step dispatch, fixed two-step dependency, skip behavior, partial failure, and Agent Run persistence.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent_team/dispatcher.py backend/src/services/session_store.py backend/src/tests/test_agent_dispatcher.py
git commit -m "feat: dispatch synchronous agent tasks"
```

---

### Task 10: Implement ConversationService Turn Orchestration

**Owner Model:** `gpt-5.5`, reasoning `high`
**Prerequisite:** Task 9 direct dispatcher and Agent Run persistence are green.
**Escalate/Stop:** Stop if orchestration requires a free loop, hidden background execution, or restoring expired Candidates after failure.

**Files:**
- Create: `backend/src/services/conversation_service.py`
- Create: `backend/src/tests/test_conversation_service.py`
- Modify: `backend/src/services/session_schemas.py`

- [ ] **Step 1: Define the Turn request/response contracts**

```python
class SessionTurnRequest(BaseModel):
    message: str = Field(min_length=1)
    experiment_log: ExperimentLogRequest | None = None
    idempotency_key: str = Field(min_length=1, max_length=128)
    top_k: int = Field(default=5, ge=1, le=20)
    idea_count: int = Field(default=3, ge=3, le=5)


class SessionTurnResponse(BaseModel):
    session_id: str
    turn_id: str
    status: Literal["running", "completed", "failed"]
    assistant_message: str = ""
    plan: LeaderPlan | None = None
    active_candidates: list[SessionCandidate] = Field(default_factory=list)
    knowledge: KnowledgeResult = Field(default_factory=lambda: KnowledgeResult(enabled=False))
    ideas: list[IdeaOption] = Field(default_factory=list)
    agent_runs: list[AgentRunSummary] = Field(default_factory=list)
    errors: list[AgentError] = Field(default_factory=list)
```

- [ ] **Step 2: Write failing orchestration tests**

Cover:

```python
def test_new_turn_expires_old_candidates_before_planning(service, seeded_active_batch):
    response = service.run("default", make_request("Explain the current status"))
    assert response.status == "completed"
    assert service.candidate_service.list_active("default") == []


def test_research_success_and_idea_failure_returns_partial_success(service_with_failing_idea):
    response = service_with_failing_idea.run("default", make_research_then_idea_request())
    assert response.status == "completed"
    assert response.active_candidates
    assert response.ideas == []
    assert response.errors[0].agent_name == "idea"


def test_idempotent_retry_returns_original_response(service):
    request = make_request("Find papers", idempotency_key="same-key")
    assert service.run("default", request) == service.run("default", request)
    assert service.planner.call_count == 1


def test_turn_timeout_marks_turn_failed(service_with_expired_deadline):
    with pytest.raises(TurnTimeoutError):
        service_with_expired_deadline.run("default", make_request("Find papers"))
    assert service_with_expired_deadline.store.latest_turn("default")["status"] == "failed"
```

- [ ] **Step 3: Implement the orchestration sequence**

`ConversationService.run()` must execute exactly:

```python
start = self.store.start_turn(session_id, request.idempotency_key, {"text": request.message})
if start.replayed:
    replay = self.store.get_replayed_response(session_id, start.turn_id)
    if replay is not None:
        return SessionTurnResponse(**replay)
    return SessionTurnResponse(session_id=session_id, turn_id=start.turn_id, status=start.status)

context = self.context_builder.build(session_id)
try:
    retrieval = self.knowledge_retrieval.search(request.message, top_k=request.top_k)
    context = context.model_copy(update={"current_knowledge": retrieval.results})
except RetrievalServiceError:
    context = context.model_copy(update={"current_knowledge": []})
planner_input = self._planner_input(request, context)
plan = self.planner.plan(planner_input)
plan = self.validator.validate(plan, experiment_log=request.experiment_log)
results = self.dispatcher.execute(
    session_id,
    start.turn_id,
    plan,
    request.experiment_log,
    context,
)
assistant_message = self.responder.respond(planner_input, plan, results)
response = self._response(session_id, start.turn_id, plan, results, assistant_message)
self.store.complete_turn(start.turn_id, response.model_dump(mode="json"), plan.model_dump(mode="json"))
self.summary_service.maybe_refresh(session_id)
return response
```

`_planner_input()` sets `has_knowledge=bool(context.current_knowledge)`. Knowledge dispatch passes `context.current_knowledge` to `KnowledgeQAService.answer(retrieved_results=...)` to avoid duplicate retrieval. Before planning, before each Step, and before response generation, compare a monotonic deadline based on `turn_timeout_seconds`; expiration raises `TurnTimeoutError`, persists the failed Turn, and never restores expired Candidates.

Catch `PlanValidationError` and produce a clarification response without dispatch. Catch expected service failures as structured partial errors. On an unexpected exception, call `fail_turn()` and re-raise.

- [ ] **Step 4: Ensure direct reply and clarification remain bounded**

`direct_reply` and `clarify` execute no professional Agent Run. Clarification uses `plan.clarification_question`; direct reply uses `LeaderResponder`. Neither creates a Candidate Batch.

- [ ] **Step 5: Run orchestration tests and Phase 3 review**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_conversation_service.py backend/src/tests/test_agent_dispatcher.py backend/src/tests/test_leader_planner.py -q
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
git diff --check
```

Expected: PASS. Review that Leader is the only user-facing component, no loops exist, Research exclusively owns fresh Candidate creation, and Idea receives evidence rather than running fresh discovery.

- [ ] **Step 6: Commit**

```bash
git add backend/src/services/conversation_service.py backend/src/services/session_schemas.py backend/src/tests/test_conversation_service.py
git commit -m "feat: orchestrate persistent agent turns"
```

---

### Task 11: Expose Session, Candidate, And Saved Paper APIs

**Owner Model:** `gpt-5.4`, reasoning `medium`
**Prerequisite:** Task 10 service contracts and error semantics are committed.
**Escalate/Stop:** Stop if HTTP wiring would change domain semantics instead of mapping typed service outcomes.

**Files:**
- Modify: `backend/src/main.py`
- Create: `backend/src/tests/test_session_api.py`
- Modify: `backend/src/tests/test_api_mvp.py`

- [ ] **Step 1: Write failing API contract tests**

```python
def test_default_session_turn_and_history(client):
    response = client.post(
        "/sessions/default/turns",
        json={"message": "Find papers", "idempotency_key": "api-1"},
    )
    assert response.status_code == 200
    turn = response.json()
    assert turn["session_id"] == "default"
    assert turn["status"] == "completed"

    history = client.get("/sessions/default/messages").json()
    assert [item["role"] for item in history["items"]] == ["user", "assistant"]


def test_expired_candidate_accept_returns_409(client, expired_candidate):
    response = client.post(f"/sessions/default/candidates/{expired_candidate.id}/accept")
    assert response.status_code == 409
    assert response.json()["detail"] == "Candidate expired"
```

- [ ] **Step 2: Add dependency constructors**

Add cached or request-scoped constructors for `SessionStore`, `CandidateLifecycleService`, Context/Summary services, Leader Planner/Responder, Research/Idea Agents, Direct Dispatcher, and `ConversationService`. All must use the same configured SQLite path and existing discovery/QA/Idea dependencies.

- [ ] **Step 3: Add endpoints**

```python
@app.post("/sessions/{session_id}/turns", response_model=SessionTurnResponse)
def create_session_turn(session_id: str, request: SessionTurnRequest, service=Depends(get_conversation_service)):
    try:
        return service.run(session_id, request)
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/sessions/{session_id}/messages", response_model=MessagePage)
def list_session_messages(session_id: str, before_id: int | None = None, limit: int = 50, store=Depends(get_session_store)):
    return store.message_page(session_id, before_id=before_id, limit=min(max(limit, 1), 100))


@app.get("/sessions/{session_id}/candidates/active", response_model=list[SessionCandidate])
def list_active_candidates(session_id: str, service=Depends(get_candidate_lifecycle_service)):
    return service.list_active(session_id)


@app.post("/sessions/{session_id}/candidates/{candidate_id}/accept", response_model=CandidateAcceptResponse)
def accept_session_candidate(session_id: str, candidate_id: str, service=Depends(get_candidate_lifecycle_service)):
    try:
        return service.accept(session_id, candidate_id)
    except CandidateExpiredError as exc:
        raise HTTPException(status_code=409, detail="Candidate expired") from exc


@app.get("/papers", response_model=list[SavedPaper])
def list_saved_papers(store: MemoryStore = Depends(get_memory_store)):
    return store.list_saved_papers()
```

- [ ] **Step 4: Preserve compatibility**

Keep `/research/assistant`, `/research/query`, `/papers/candidates`, and `/papers/{paper_id}/accept`. Add deprecation text to the OpenAPI description of legacy Candidate endpoints, but do not change their current behavior in this task.

- [ ] **Step 5: Run API and backend tests**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_session_api.py backend/src/tests/test_api_mvp.py -q
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
```

Expected: PASS for Turn creation, replay, history pagination, Session busy, active Candidates, 409 expiry, Saved Papers, and legacy endpoints.

- [ ] **Step 6: Commit**

```bash
git add backend/src/main.py backend/src/tests/test_session_api.py backend/src/tests/test_api_mvp.py
git commit -m "feat: expose persistent session api"
```

---

### Task 12: Build The Session Chat Frontend

**Owner Model:** `gpt-5.4`, reasoning `medium`
**Prerequisite:** Task 11 Session API tests are green.
**Escalate/Stop:** Do not add multi-Session navigation, independent Agent chats, or streaming behavior.

**Files:**
- Modify: `frontend/src/api.js`
- Create: `frontend/src/components/SessionChatPanel.vue`
- Create: `frontend/src/components/__tests__/SessionChatPanel.test.js`
- Modify: `frontend/src/components/ResearchWorkbench.vue`
- Modify: `frontend/src/components/__tests__/ResearchWorkbench.test.js`

- [ ] **Step 1: Add failing chat component tests**

```js
test("renders history and submits one idempotent turn", async () => {
  const runTurn = vi.fn().mockResolvedValue({
    turn_id: "turn-2",
    status: "completed",
    assistant_message: "I found fresh papers.",
  });
  const wrapper = mount(SessionChatPanel, {
    props: {
      messages: [
        { id: 1, role: "user", content: { text: "Earlier question" } },
        { id: 2, role: "assistant", content: { assistant_message: "Earlier answer" } },
      ],
      runTurn,
    },
  });

  await wrapper.find("textarea").setValue("Find fresh papers");
  await wrapper.find("form").trigger("submit.prevent");

  expect(runTurn).toHaveBeenCalledWith(expect.objectContaining({
    message: "Find fresh papers",
    idempotency_key: expect.any(String),
  }));
  expect(wrapper.text()).toContain("Earlier answer");
});
```

- [ ] **Step 2: Add Session API clients**

```js
export function createSessionTurn(sessionId, payload) {
  return request(`/sessions/${sessionId}/turns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getSessionMessages(sessionId, beforeId = null) {
  const query = beforeId ? `?before_id=${beforeId}` : "";
  return request(`/sessions/${sessionId}/messages${query}`);
}

export function getActiveCandidates(sessionId) {
  return request(`/sessions/${sessionId}/candidates/active`);
}

export function acceptSessionCandidate(sessionId, candidateId) {
  return request(`/sessions/${sessionId}/candidates/${candidateId}/accept`, { method: "POST" });
}

export function getSavedPapers() {
  return request("/papers");
}
```

- [ ] **Step 3: Implement `SessionChatPanel.vue`**

Requirements:

- Render user and assistant messages from `content.text` and `content.assistant_message`.
- Generate one `crypto.randomUUID()` idempotency key when submission starts and reuse it for a manual retry of the same failed draft.
- Disable submission while busy or while text is empty.
- Emit `turn-completed` with the response and `turn-failed` with the error.
- Do not render internal Agent messages as separate chat speakers; traces belong in `AgentTracePanel`.

- [ ] **Step 4: Make the default Session the workbench primary path**

In `ResearchWorkbench.vue`:

- Set `const sessionId = "default"`.
- Load Session messages, active Candidates, Saved Papers, health, and memory summary on mount.
- On Turn success, reload messages and active Candidates and store the latest Turn response.
- On Turn submission start, clear active Candidate UI immediately because backend start semantics expire them.
- Keep Research Query and legacy Idea Assistant in a collapsed `Legacy tools` section during the compatibility window.

- [ ] **Step 5: Run frontend chat tests**

```bash
cd frontend
npm test -- src/components/__tests__/SessionChatPanel.test.js src/components/__tests__/ResearchWorkbench.test.js
npm run build
```

Expected: PASS and no duplicate assistant summary/chat output.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.js frontend/src/components/SessionChatPanel.vue frontend/src/components/ResearchWorkbench.vue frontend/src/components/__tests__/SessionChatPanel.test.js frontend/src/components/__tests__/ResearchWorkbench.test.js
git commit -m "feat: add persistent session chat"
```

---

### Task 13: Add Active Candidate, Saved Paper, And Agent Trace UI

**Owner Model:** `gpt-5.4`, reasoning `medium`
**Prerequisite:** Task 12 default Session chat is committed and green.
**Escalate/Stop:** Stop if the UI must infer domain state not returned by the API or makes expired history actionable.

**Files:**
- Create: `frontend/src/components/ActiveCandidatesPanel.vue`
- Create: `frontend/src/components/AgentTracePanel.vue`
- Create: `frontend/src/components/__tests__/ActiveCandidatesPanel.test.js`
- Create: `frontend/src/components/__tests__/AgentTracePanel.test.js`
- Modify: `frontend/src/components/CandidateLifecyclePanel.vue`
- Modify: `frontend/src/components/ResearchWorkbench.vue`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write failing active-candidate tests**

```js
test("only active candidates expose Accept", async () => {
  const accept = vi.fn().mockResolvedValue({ status: "accepted", paper_id: "paper-1" });
  const wrapper = mount(ActiveCandidatesPanel, {
    props: {
      candidates: [makeSessionCandidate({ id: "candidate-1", status: "active" })],
      acceptCandidate: accept,
    },
  });

  await wrapper.get("button").trigger("click");
  expect(accept).toHaveBeenCalledWith("candidate-1");
  expect(wrapper.text()).toContain("Accepted");
});
```

Add a 409 case that removes the expired card and displays `Candidate expired; ask the Leader to search again.`

```js
test("removes a candidate when Accept reports expiration", async () => {
  const expired = Object.assign(new Error("Candidate expired"), { status: 409 });
  const wrapper = mount(ActiveCandidatesPanel, {
    props: {
      candidates: [makeSessionCandidate({ id: "candidate-1", status: "active" })],
      acceptCandidate: vi.fn().mockRejectedValue(expired),
    },
  });

  await wrapper.get("button").trigger("click");
  expect(wrapper.text()).toContain("Candidate expired; ask the Leader to search again.");
  expect(wrapper.text()).not.toContain("Candidate paper title");
});
```

- [ ] **Step 2: Implement `ActiveCandidatesPanel.vue`**

Render `paper_snapshot`, judgement scores, and one Accept action. The component receives only active Candidates from the API; it must not infer saved state from paper lifecycle statuses.

- [ ] **Step 3: Implement `AgentTracePanel.vue`**

Render:

- Plan type and goal.
- Ordered Agent Runs with `completed|failed|skipped` badges.
- Typed errors with Agent name and message.
- A collapsed-by-default details region.

Do not show raw prompts, provider credentials, or full internal context.

- [ ] **Step 4: Relabel the existing lifecycle panel as Saved Papers**

`CandidateLifecyclePanel.vue` now receives only `/papers` results. Update empty state and headings from `candidate` terminology to `Saved Papers`, while keeping upload and embed actions unchanged.

- [ ] **Step 5: Wire refresh behavior**

After Accept:

- Remove the item from active Candidates.
- Reload Saved Papers and Memory Summary.
- Keep the historical chat snapshot unchanged and read-only.

- [ ] **Step 6: Run component and workbench tests**

```bash
cd frontend
npm test
npm run build
```

Expected: PASS for active-only actions, 409 removal, saved lifecycle, trace rendering, history preservation, and build.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/ActiveCandidatesPanel.vue frontend/src/components/AgentTracePanel.vue frontend/src/components/CandidateLifecyclePanel.vue frontend/src/components/ResearchWorkbench.vue frontend/src/components/__tests__/ActiveCandidatesPanel.test.js frontend/src/components/__tests__/AgentTracePanel.test.js frontend/src/styles.css
git commit -m "feat: separate active candidates and saved papers"
```

---

### Task 14: Add Planner Eval, Offline Session Smoke, And Documentation

**Owner Model:** `gpt-5.4`, reasoning `medium`
**Prerequisite:** Tasks 11-13 pass backend API, frontend component, and build tests.
**Escalate/Stop:** The user must review Eval labels; stop if documentation would overclaim Mailbox, multi-Session, autonomy, or production scale.

**Files:**
- Create: `backend/src/evals/leader_planner_cases.json`
- Create: `backend/src/tests/test_leader_planner_eval.py`
- Modify: `backend/scripts/smoke_offline_mvp.sh`
- Modify: `README.md`
- Modify: `docs/interview/demo_script.md`
- Modify: `docs/interview/interview-qna.md`

- [ ] **Step 1: Create the initial Planner Eval dataset**

Create these 12 initial cases; the user reviews their labels before implementation proceeds:

```json
[
  {
    "id": "research_recent_papers",
    "message": "Find recent papers about graph reconstruction",
    "has_knowledge": false,
    "experiment_log": null,
    "expected_plan_type": "research"
  },
  {
    "id": "idea_with_coverage",
    "message": "Use this experiment to propose the next small test",
    "has_knowledge": true,
    "experiment_log": {
      "task": "graph reconstruction",
      "model": "GNN",
      "dataset": "local benchmark",
      "metric_problem": "precision is low",
      "tried_methods": ["threshold tuning"],
      "observation": "recall improved but precision fell",
      "goal": "recover precision",
      "tags": ["evaluation"]
    },
    "expected_plan_type": "idea"
  },
  {
    "id": "reject_auto_accept",
    "message": "Search papers and automatically accept every result",
    "has_knowledge": false,
    "experiment_log": null,
    "expected_plan_type": "research",
    "forbidden_actions": ["accept_paper"]
  },
  {
    "id": "knowledge_saved_evidence",
    "message": "Explain what the saved papers say about oversmoothing",
    "has_knowledge": true,
    "experiment_log": null,
    "expected_plan_type": "knowledge_qa"
  },
  {
    "id": "research_then_idea_missing_coverage",
    "message": "Find newer evidence, then propose ideas for this experiment",
    "has_knowledge": false,
    "experiment_log": {
      "task": "graph reconstruction",
      "model": "GNN",
      "dataset": "local benchmark",
      "metric_problem": "precision is low",
      "tried_methods": ["threshold tuning"],
      "observation": "recall improved but precision fell",
      "goal": "recover precision",
      "tags": ["evaluation"]
    },
    "expected_plan_type": "research_then_idea"
  },
  {
    "id": "clarify_short_request",
    "message": "Improve it",
    "has_knowledge": false,
    "experiment_log": null,
    "expected_plan_type": "clarify"
  },
  {
    "id": "direct_product_question",
    "message": "What can this research workbench do?",
    "has_knowledge": false,
    "experiment_log": null,
    "expected_plan_type": "direct_reply"
  },
  {
    "id": "idea_missing_experiment",
    "message": "Generate an experiment idea but I have not supplied the experiment details",
    "has_knowledge": true,
    "experiment_log": null,
    "expected_plan_type": "clarify"
  },
  {
    "id": "unknown_agent_request",
    "message": "Create a statistics agent and let it decide",
    "has_knowledge": false,
    "experiment_log": null,
    "expected_plan_type": "clarify",
    "forbidden_actions": ["create_agent"]
  },
  {
    "id": "avoid_duplicate_search",
    "message": "Answer from the evidence already saved; do not search again",
    "has_knowledge": true,
    "experiment_log": null,
    "expected_plan_type": "knowledge_qa",
    "forbidden_actions": ["recommend_papers"]
  },
  {
    "id": "chinese_research_request",
    "message": "帮我找最新的图重建论文",
    "has_knowledge": false,
    "experiment_log": null,
    "expected_plan_type": "research"
  },
  {
    "id": "chinese_idea_with_coverage",
    "message": "根据这次实验给我下一步的小实验建议",
    "has_knowledge": true,
    "experiment_log": {
      "task": "图重建",
      "model": "GNN",
      "dataset": "本地基准",
      "metric_problem": "精度偏低",
      "tried_methods": ["阈值调整"],
      "observation": "召回提升但精度下降",
      "goal": "恢复精度",
      "tags": ["评估"]
    },
    "expected_plan_type": "idea"
  },
  {
    "id": "ambiguous_research_scope",
    "message": "帮我研究一下",
    "has_knowledge": false,
    "experiment_log": null,
    "expected_plan_type": "clarify"
  }
]
```

- [ ] **Step 2: Add deterministic Eval assertions**

```python
@pytest.mark.parametrize("case", load_cases())
def test_deterministic_planner_eval(case):
    plan = DeterministicLeaderPlanner().plan(planner_input_from_case(case))
    PlanValidator().validate(plan, experiment_log=planner_input_from_case(case).experiment_log)

    assert plan.plan_type == case["expected_plan_type"]
    actions = [step.action for step in plan.steps]
    assert not set(actions).intersection(case.get("forbidden_actions", []))
```

- [ ] **Step 3: Extend offline smoke with a full Session lifecycle**

Add smoke assertions in this order:

1. POST first research Turn and capture active Candidate IDs.
2. POST a second Turn and assert the first unaccepted Candidates are absent from `/sessions/default/candidates/active`.
3. POST another research Turn, Accept one active Candidate, and assert it appears in `/papers` with `accepted` status.
4. Confirm message history contains paired user/assistant messages.
5. Confirm `/research/assistant` still returns V1 compatibility fields.

Print:

```text
SESSION_TURN_STATUS=completed
SESSION_MESSAGE_COUNT=6
ACTIVE_CANDIDATE_REFRESH_OK=true
SESSION_CANDIDATE_ACCEPTED_STATUS=accepted
AGENT_TEAM_V3_SMOKE_OK=true
```

- [ ] **Step 4: Update truthful product and interview documentation**

Document:

- Default permanent Session, not multi-Session UI.
- Bounded synchronous Agent Team, not autonomous free-loop agents.
- Logical Agent persistence, not resident processes.
- Active Candidate vs Saved Paper vs Confirmed Memory boundaries.
- On-demand Research then Idea.
- SQLite Mailbox as a future Dispatcher replacement, not an implemented capability.

- [ ] **Step 5: Run final verification**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
cd frontend
npm test
npm run build
cd ..
backend/scripts/smoke_offline_mvp.sh
git diff --check
```

Expected: all commands PASS, smoke prints both `OFFLINE_MVP_SMOKE_OK=true` and `AGENT_TEAM_V3_SMOKE_OK=true`, and the worktree contains no generated database, upload, vector, coverage, or build artifacts.

- [ ] **Step 6: Review against all V3 success criteria**

Confirm with direct evidence:

- Multi-turn messages persist in `default`.
- Context uses summary plus six recent Turns.
- New Turns expire prior unaccepted Candidates.
- Refresh excludes Saved Papers and the most recent expired Batch.
- Accept is transactional and idempotent.
- Leader plans are typed and validated.
- Research exclusively creates Candidate Batches.
- Idea uses existing or Research-provided evidence without owning fresh discovery.
- Agent Contexts and Runs persist separately.
- Legacy endpoints remain operational.
- No Mailbox, resident Worker, dynamic Agent, or free loop was added.

- [ ] **Step 7: Commit final verification assets and docs**

```bash
git add backend/src/evals/leader_planner_cases.json backend/src/tests/test_leader_planner_eval.py backend/scripts/smoke_offline_mvp.sh README.md docs/interview/demo_script.md docs/interview/interview-qna.md
git commit -m "test: verify agent team v3 workflow"
```

---

### Task 15: Final Architecture, Concurrency, And Failure-Semantics Review

**Owner Model:** `gpt-5.5`, reasoning `high`
**Prerequisite:** Task 14 commit exists; all backend, frontend, build, Eval, and offline smoke checks are green.
**Escalate/Stop:** Do not approve completion while any state transition, persistence boundary, Agent ownership rule, or required verification remains uncertain.

**Files:**
- Create: `docs/superpowers/reviews/2026-06-30-agent-team-v3-final-review.md`
- Modify only when a finding requires a fix: files introduced or changed by Tasks 1-14
- Test: relevant focused regression test for every code fix

- [ ] **Step 1: Verify the handoff and commit chain**

Run:

```bash
git status --short --branch
git log --oneline --decorate --max-count=20
git diff --check
```

Expected: clean V3 worktree, all wave commits present in order, and no diff-check errors.

- [ ] **Step 2: Dispatch four read-only review subagents**

Use fresh review agents with these non-overlapping scopes:

```text
Reviewer A: Trace every V3 spec success criterion to code and tests; report missing or contradictory behavior with file references.
Reviewer B: Audit SQLite transactions, one-running-Turn enforcement, idempotent replay, Candidate expiration/Accept, WAL/busy timeout, and failure terminal states.
Reviewer C: Audit typed Planner/Validator, Agent ownership, coverage routing, Research-to-Idea evidence transfer, timeouts, and prohibition of loops/dynamic Agents/auto-Accept.
Reviewer D: Audit FastAPI mappings and Vue behavior for history pagination, active-vs-saved separation, 409 expiry, stale UI clearing, trace safety, and legacy compatibility.
```

Each reviewer returns only evidence-backed findings categorized as blocking, important, or optional. Reviewers do not edit files.

- [ ] **Step 3: Consolidate findings against frozen invariants**

Treat these as blocking:

- More than one running Turn per Session can be created.
- A failed new Turn restores an expired Candidate.
- An expired Candidate can be accepted.
- Saved Paper write and Candidate Accept are not atomic or idempotent.
- Idea initiates fresh Discovery or creates Candidate Batches.
- Leader executes an unvalidated plan or unknown Action.
- Research failure does not skip a dependent Idea step.
- Provider failure is mislabeled as no evidence.
- Full permanent history is inserted into Agent context.
- Automated verification requires live network providers.

- [ ] **Step 4: Fix blocking or important findings with focused RED/GREEN loops**

For each accepted finding:

1. Add one focused regression test in the owning test file.
2. Run only that test and confirm RED for the reported behavior.
3. Apply the smallest fix without expanding the frozen scope.
4. Re-run the focused test and the owning test module.
5. Record the finding, test, fix, and result in the review document.

Optional findings are documented but not implemented unless they directly improve correctness without expanding scope.

- [ ] **Step 5: Run final independent verification**

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
cd frontend
npm test
npm run build
cd ..
backend/scripts/smoke_offline_mvp.sh
git diff --check
git status --short
```

Expected: all tests and build PASS; smoke prints `OFFLINE_MVP_SMOKE_OK=true` and `AGENT_TEAM_V3_SMOKE_OK=true`; only the review report and intentional review fixes are uncommitted.

- [ ] **Step 6: Write the final review report**

Use these sections in `2026-06-30-agent-team-v3-final-review.md`:

```markdown
# Agent Team V3 Final Review

## Reviewed Commit Range
## Spec Traceability Result
## Transaction And Concurrency Result
## Planner And Agent Boundary Result
## API And Frontend Result
## Findings Fixed
## Accepted Optional Findings
## Verification Evidence
## Final Decision
```

`Final Decision` must be either `approved` or `not approved`, followed by concrete evidence. Do not use conditional approval wording.

- [ ] **Step 7: Commit the review and any verified fixes**

```bash
git add backend frontend docs/superpowers/reviews/2026-06-30-agent-team-v3-final-review.md
git commit -m "review: verify agent team v3 architecture"
```

---

## Post-Implementation Handoff

After Task 15:

1. Use `superpowers:verification-before-completion` and record exact backend, frontend, build, smoke, and diff-check output.
2. Use `superpowers:requesting-code-review` for final spec and code-quality review.
3. Use `superpowers:finishing-a-development-branch` to choose local merge, push/PR, or worktree cleanup.
4. Do not begin multi-Session or SQLite Mailbox work without a separate approved spec and plan.

## Execution Log

Append one record after each completed model wave. Never rewrite earlier records; corrections are added as a new record.

```text
Wave:
Owner model:
Completed task commits:
Current worktree and branch:
Verification commands and results:
Contract decisions made:
Known failures or blockers:
Next unblocked wave:
```

```text
Wave: 1
Owner model: GPT-5.5 high responsibility (current highest-capability agent; runtime model selection was unavailable)
Completed task commits: f33613489dc473608e901f0bcf07e0b4963433e1
Current worktree and branch: /Users/nuonuohu/Developer/graphReconstruction/.worktrees/agent-team-v3; codex/agent-team-v3
Verification commands and results: backend pytest 202 passed, 1 warning; frontend Vitest 25 passed; Vite build passed; offline smoke printed OFFLINE_MVP_SMOKE_OK=true; git diff --check passed
Contract decisions made: kept the assistant-first workbench, memory summary, collapsed saved-paper lifecycle, and fallback query; adopted V1 typed results, stage errors, grounded-QA behavior, failure emission, and stale-result clearing without duplicating summary sections
Known failures or blockers: none
Next unblocked wave: Wave 2, GPT-5.4 medium, Task 2
```

```text
Wave: 2
Owner model: GPT-5.5 high responsibility (user-directed override to continue execution from Wave 2 in the existing V3 worktree)
Completed task commits:
Current worktree and branch: /Users/nuonuohu/Developer/graphReconstruction/.worktrees/agent-team-v3; codex/agent-team-v3
Verification commands and results: migration RED reproduced on backend/src/tests/test_sqlite_migrations.py; memory-store RED reproduced on backend/src/tests/test_memory_store.py; backend pytest backend/src/tests/test_sqlite_migrations.py backend/src/tests/test_memory_store.py passed twice with 27 passed in 0.14s on the final run; spec review approved after fixing migration atomicity; code-quality review approved after replacing INSERT OR REPLACE with ON CONFLICT DO UPDATE and adding a child-row resave regression test
Contract decisions made: kept Task 2 scope limited to versioned SQLite migrations plus connection pragmas; each migration version now applies atomically with its schema_migrations record; MemoryStore paper saves preserve existing child rows under foreign key enforcement by using UPSERT instead of REPLACE
Known failures or blockers: none
Next unblocked wave: Wave 3, GPT-5.5 high, Tasks 3-4
```

```text
Wave: 3
Owner model: GPT-5.5 high responsibility
Completed task commits: cd63ca81f9a67d409fbd8f6977488dc1271f5ae6; 659e304f8b9727385c9f44fc8c357bcdb55ab12f; prior Wave 2 task commit was 6732527398af4ec3df463f642bce7b141d3e0d5d
Current worktree and branch: /Users/nuonuohu/Developer/graphReconstruction/.worktrees/agent-team-v3; codex/agent-team-v3
Verification commands and results: backend pytest backend/src/tests/test_session_store.py passed with 11 passed in 0.09s; backend pytest backend/src/tests/test_candidate_lifecycle.py backend/src/tests/test_memory_store.py passed with 30 passed in 0.19s; cross-task backend pytest backend/src/tests/test_session_store.py backend/src/tests/test_candidate_lifecycle.py backend/src/tests/test_memory_store.py passed with 41 passed in 0.23s; git diff --check passed
Contract decisions made: Session turns now own idempotent replay, single-running-turn enforcement, persisted assistant responses, failure persistence, recent-turn reads, agent contexts, and agent run storage; Session candidates now expire on the next turn, suppression combines global saved papers with the latest expired batch, Accept is atomic and idempotent, and Saved Papers stay global with statuses limited to accepted|uploaded|chunked|embedded
Known failures or blockers: Task 3 was recovered from a subagent usage-limit interruption by validating the partial implementation in the main thread; no remaining functional blocker
Next unblocked wave: Wave 4, GPT-5.4 medium, Tasks 5-6
```

```text
Wave: 4
Owner model: GPT-5.4 medium for Tasks 5-6; GPT-5.5 high-responsibility handoff for the Task 5 concurrency finding because it triggered the transaction/concurrency stop condition
Completed task commits: e33a30d86ce80f83cbcfda1f5526a9f7f7d0e184; 6677ce0bb718c8fd100ee864bc6f36b39e310c43; fab4f73ffa6495c986136ffe8b23dc9923c4afce; 12cfa2e0d0f8236fefb9f8f1a9add7bf8e5a4cde
Current worktree and branch: /Users/nuonuohu/Developer/graphReconstruction/.worktrees/agent-team-v3; codex/agent-team-v3
Verification commands and results: Task 5 focused context and store tests passed with 20 tests after the concurrency fix; Task 6 focused validator tests passed with 25 tests; final backend pytest passed with 258 tests and 1 existing deprecation warning; git diff --check passed
Contract decisions made: Session context keeps the rolling Session summary, six recent completed Turns, role-specific Agent Contexts, confirmed-only reviewed memory, and current vector knowledge separate; summary refresh uses an atomic expected-boundary CAS so stale writers cannot overwrite a newer summary or regress its boundary; Agent plans remain limited to six plan types, three Agents, and three Actions with deterministic validation through PlanValidator.validate(plan, experiment_log=...)
Known failures or blockers: none; Task 5 quality review initially found a stale summary refresh race, fixed by 6677ce0 with a real interleaving regression test; Task 6 spec review initially found two contract deviations, fixed by 12cfa2e
Next unblocked wave: Wave 5, GPT-5.5 high, Task 7
```
