# Agent Team V3 Final Review

## Reviewed Commit Range

Branch: `codex/agent-team-v3`

Reviewed Task 11-14 handoff commits at the Task 15 start point:

- `62be2fd fix: enforce default session api boundary`
- `4032aa7 docs: record agent team v3 task 11 handoff`
- `c6a33e8 feat: add persistent session chat`
- `be944fc feat: separate active candidates and saved papers`
- `a70e879 test: verify agent team v3 workflow`

Fresh handoff checks were run before review:

```text
$ git status --short --branch
## codex/agent-team-v3

$ git log --oneline --decorate --max-count=20
a70e879 (HEAD -> codex/agent-team-v3) test: verify agent team v3 workflow
be944fc feat: separate active candidates and saved papers
c6a33e8 feat: add persistent session chat
4032aa7 docs: record agent team v3 task 11 handoff
62be2fd fix: enforce default session api boundary
5322808 feat: expose persistent session api
830e6f8 docs: record agent team v3 wave 8 handoff
9b8aec3 fix: join timed out agent steps
7a1ff7f fix: enforce bounded turn deadlines
904edd0 feat: orchestrate persistent agent turns
f3f5909 docs: record agent team v3 wave 7 handoff
79705e4 feat: dispatch synchronous agent tasks
e7cabc6 docs: record agent team v3 wave 6 handoff
338ad0b feat: add research and idea agents
5f77d74 docs: record agent team v3 wave 5 handoff
439fc1a fix: complete leader provider and response wiring
5a0b5d0 fix: recognize existing experiment log review
798cc4c fix: prioritize research guard over product reply
a776a8a fix: preserve leader idea research semantics
1516c96 fix: integrate bounded research routing signal

$ git diff --check
passed with no output
```

The Task 14 Execution Log blocker saying planner eval labels still needed explicit user semantic review is resolved by the user's Task 15 handoff instruction: `backend/src/evals/leader_planner_cases.json` labels are approved as V3 product truth.

Task 15 requested four read-only review agents. Four read-only subagents were dispatched, but each errored before producing findings because of model usage limits. The four scopes were then completed locally as a read-only final review; no code was edited during review.

## Spec Traceability Result

approved

The V3 success criteria in `docs/superpowers/specs/2026-06-30-agent-team-v3-design.md` trace to implementation and regression coverage:

- Default persistent Session and bounded history: `SessionStore.start_turn()` persists user messages, enforces idempotency, and expires prior active candidate batches inside `BEGIN IMMEDIATE`; `SessionContextBuilder.build()` includes the rolling summary, only six recent completed Turns, confirmed memory, agent contexts, and current knowledge.
- Typed Leader planning and validation: `LeaderPlan`/`PlanStep` literals bound plan types, agents, and actions; `PlanValidator.validate()` rejects step sequence mismatches, duplicate IDs, forbidden dependencies, missing experiment logs for Idea plans, and malformed clarification plans.
- Leader-only user entry and fixed Agent ownership: FastAPI exposes `/sessions/default/turns`; Research owns fresh discovery and Candidate Batch creation; Idea receives `research_candidates` and calls `IdeaRecommendationService.recommend(..., include_discovery=False)`.
- Research-to-Idea evidence transfer: `DirectAgentDispatcher` passes the completed Research result's `top_k` to the dependent Idea step.
- Offline planner eval product truth: `backend/src/evals/leader_planner_cases.json` covers Research, Idea, Research then Idea, Knowledge QA, direct replies, clarification, Chinese requests, duplicate-search suppression, and forbidden auto-accept/dynamic-agent actions; `test_leader_planner_eval.py` validates every case through `PlanValidator`.
- Offline verification remains deterministic and does not require live network providers.

No blocking, important, or optional traceability finding was accepted.

## Transaction And Concurrency Result

approved

SQLite and lifecycle invariants are implemented with transactional boundaries and focused tests:

- Migrations create `one_running_turn_per_session`, `one_active_batch_per_session`, status checks, foreign keys, WAL mode, and `busy_timeout`; each migration version is applied under `BEGIN IMMEDIATE`.
- `SessionStore.start_turn()` starts `BEGIN IMMEDIATE`, replays the same idempotency key before creating a new Turn, rejects an existing running Turn, inserts the user message, and expires active candidate items and batches in the same transaction.
- `SessionStore.complete_turn()` and `fail_turn()` require the Turn to still be `running` before writing terminal state.
- `CandidateLifecycleService.accept()` runs under `BEGIN IMMEDIATE`; expired candidates raise `CandidateExpiredError`, accepted candidates replay idempotently, and paper upsert plus Candidate accept are committed atomically.
- Tests cover one-running-turn rejection, idempotent replay, expiry before planning, expired Candidate 409 behavior, atomic/idempotent Accept, failed terminal state persistence, timeout terminal states, and nonfatal summary refresh after completion.

The frozen blocking invariants were not violated: more than one running Turn per Session was not possible, failed Turns do not restore expired Candidates, expired Candidates cannot be accepted, Accept is atomic/idempotent, and terminal failed states are persisted.

No blocking, important, or optional transaction/concurrency finding was accepted.

## Planner And Agent Boundary Result

approved

Planner, Validator, dispatcher, and Agent ownership boundaries match the frozen V3 architecture:

- `PlanValidator` fixes the allowed step sequences for `direct_reply`, `clarify`, `knowledge_qa`, `research`, `idea`, and `research_then_idea`; loops and dynamic dependency shapes are rejected.
- Unknown actions are rejected at schema validation time.
- Invalid Leader plans are converted to clarification without dispatching professional Agents.
- `DirectAgentDispatcher` executes the already validated plan, starts one persisted Agent Run per step, skips dependents when dependencies fail or time out, and persists terminal run states.
- Research failure is typed and does not create a Candidate Batch; dependent Idea steps are skipped.
- Knowledge provider failure is not mislabeled as no evidence: `QAServiceError` becomes a failed Knowledge Agent result with `knowledge_answer` error.
- Idea never launches fresh discovery in the Agent Team path; it passes supplied Research evidence with `include_discovery=False`.
- Timeout behavior follows the Task 10 contract: the running callable is joined before terminal persistence, then the elapsed timeout owns the result and dependent steps are skipped.
- Agent context persistence stores compact role summaries, not full prompt/history payloads.

No blocking, important, or optional planner/agent-boundary finding was accepted.

## API And Frontend Result

approved

FastAPI and Vue behavior match Task 11-14 requirements:

- The session API is restricted to the default permanent Session; non-default session routes return 404 without creating records.
- `/sessions/default/messages` bounds `limit` to 1-100 and supports `before_id` pagination.
- `/sessions/default/candidates/active` is separate from `/papers`; `/papers` returns saved papers, not unaccepted active candidates.
- Expired Candidate accept maps to HTTP 409 with `Candidate expired`; missing candidates map to 404.
- Frontend session submit clears stale saved/active candidate state before the new Turn, reloads messages and active candidates on success, and clears stale assistant result display after later assistant failure.
- Active Candidate accept removes the candidate from the UI and refreshes Saved Papers and Memory Summary.
- Active Candidate 409 expiry removes the stale card and shows an expiry message.
- Trace display exposes only the bounded plan, Agent Run summaries, and typed errors returned by `SessionTurnResponse`; persisted run inputs/outputs and prompts are not exposed through the frontend trace.
- Legacy query tools and legacy `/research/assistant` compatibility remain covered by tests and smoke.

No blocking, important, or optional API/frontend finding was accepted.

## Findings Fixed

None.

No evidence-backed blocking or important finding was accepted, so no Tasks 1-14 code was modified and no RED/GREEN fix loop was required.

## Accepted Optional Findings

None.

## Verification Evidence

Final verification was run fresh after the review pass:

```text
$ PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
458 passed, 1 warning in 6.39s
warning: existing StarletteDeprecationWarning from fastapi.testclient/httpx

$ cd frontend && npm test
Test Files  12 passed (12)
Tests  31 passed (31)
Duration  1.06s

$ cd frontend && npm run build
vite v7.3.5 building client environment for production...
23 modules transformed.
dist/index.html                  0.41 kB
dist/assets/index-CAfQp-GB.css   6.67 kB
dist/assets/index-DDaLWaqW.js   98.44 kB
built in 272ms

$ backend/scripts/smoke_offline_mvp.sh
HEALTH_STATUS=ok
SESSION_TURN_STATUS=completed
ACTIVE_CANDIDATE_REFRESH_OK=true
SESSION_MESSAGE_COUNT=6
SESSION_CANDIDATE_ACCEPTED_STATUS=accepted
AGENT_TEAM_V3_SMOKE_OK=true
EXPERIMENT_LOG_COUNT=3
MEMORY_CANDIDATE_COUNT=7
MEMORY_ACCEPTED_STATUS=confirmed
IDEA_MODE=deterministic
IDEA_COUNT=3
IDEA_EVIDENCE_COUNT=1
IDEA_EVIDENCE_PAPER_ID=idea-evidence-paper-1
OFFLINE_MVP_SMOKE_OK=true

$ git diff --check
passed with no output

$ git status --short
?? docs/superpowers/reviews/
```

## Final Decision

approved

Evidence: handoff checks were clean, commit chain matched the Task 15 start point, the Task 14 planner labels blocker was explicitly resolved by user approval, all four Task 15 review scopes found no accepted blocking/important/optional findings, and final backend, frontend, build, offline smoke, and diff-check verification passed.
