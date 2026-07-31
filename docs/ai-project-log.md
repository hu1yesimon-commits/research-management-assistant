# AI Project Log

## Current snapshot

- Goal: build a stable, bounded research workflow whose natural-language state, routes, retrieval, grounded answers, and user-controlled persistence can be evaluated separately and end to end.
- Current validated capability: the deterministic evaluator now validates Gold and structured observation schemas, scores state/route/retrieval/answer observations, enforces hard gates, and runs a synthetic contract probe in CI without network access.
- Current increment: deterministic observed-output evaluator harness and CI contract probe.
- Architecture level: strengthened at configuration and evaluation boundaries; unchanged at workflow orchestration and Provider selection.
- Key constraints: context is not evidence; only retrieved chunks support paper claims; persistent actions require user control; ordinary tests must not inherit personal real-provider settings.
- Open risks: Gold labels still require human review; current V3 plan types, state representation, chunk identity, and answer schema do not yet map directly to the Gold observation contract; real Provider behavior remains unvalidated.
- Next decision: align one V3 runtime path to the observation contract and produce the first honest draft baseline before choosing a real Provider smoke.
- Last updated: 2026-07-31

## Active assumptions

| ID | Assumption | Evidence needed | Status |
| --- | --- | --- | --- |
| A-001 | Session Summary improves research alignment with less noise than raw messages. | Paired ablation on fixed scenarios, chunks, prompts, and repeated runs. | open |
| A-002 | One shared scenario corpus can support component, workflow, and end-to-end evaluation without hiding failure causes. | Run the implemented state, route, retrieval, and answer evaluators on V3 runtime observations and inspect failure localization. | partially supported |
| A-003 | Experiment Improvement is the best first vertical workflow for testing summary, preference, retrieval, answer, and fallback boundaries together. | Human label review and first evaluator results. | open |
| A-004 | One-dimensional time-series classification and localization cases are representative enough for the first domain-focused Gold Set. | User review of scenario realism and missing failure modes. | open |
| A-005 | Explicit runtime profiles prevent personal real-provider settings from contaminating ordinary tests and offline development. | Profile-switch tests, full backend tests without Provider overrides, and offline smoke. | supported |

## Decisions

### D-001 — 2026-07-28 — Use bounded workflow authority

- Context: the research journey contains explicit lifecycle and evidence boundaries.
- Options considered: unconstrained AI routing; fully deterministic intent rules; structured LLM proposal plus deterministic validation.
- Evidence: existing V3 already uses Typed Plans and a Validator, while the desired workflow has enumerable routes and forbidden actions.
- Decision: let models propose structured state and ambiguous intent; let code authorize routes, actions, evidence, fallback, and persistence.
- Consequences: evaluation must cover both semantic quality and deterministic violations.
- Revisit when: fixed workflows demonstrably fail on representative cases requiring dynamic planning.

### D-002 — 2026-07-28 — Separate task context from evidence

- Context: Grounded Answers need Session Summary and confirmed preferences to remain aligned with the current research process.
- Options considered: query plus chunks only; raw message history; structured summary and selected preferences.
- Evidence: structured summary preserves goals, attempts, decisions, constraints, and unresolved problems while chunks remain the only paper-fact source.
- Decision: compose Grounded Answers from system policy, confirmed preferences, Session Summary, current task, and retrieved chunks; forbid summary or preferences from becoming citations.
- Consequences: custom evaluation must detect summary-as-evidence violations.
- Revisit when: ablation shows no alignment benefit or unacceptable faithfulness/cost regression.

### D-003 — 2026-07-28 — Use one scenario corpus with layered evaluators

- Context: a Grounded Answer score cannot evaluate the whole Agent, while one end-to-end score cannot locate failures.
- Options considered: answer-only Gold Set; end-to-end-only Gold Set; separate unrelated datasets; unified scenarios with scoped labels.
- Evidence: the same research scenario can expose expected state, route, relevant chunk IDs, answer constraints, and final outcome.
- Decision: use one versioned Scenario Schema and run state, route, retrieval, answer, ablation, and end-to-end views independently.
- Consequences: report hard gates and metric vectors before considering a weighted total score.
- Revisit when: shared cases make labels ambiguous or couple component tests to irrelevant fields.

### D-004 — 2026-07-28 — Do not infer research domain from repository name

- Context: `graphReconstruction` names an intended LangGraph refactor, not a Graph Reconstruction research topic.
- Options considered: keep Graph Reconstruction as a convenient fixture domain; use generic placeholders; use the user-confirmed primary research domain.
- Evidence: the user confirmed that their main research topic is one-dimensional time-series model classification and localization.
- Decision: use one-dimensional time-series classification and localization for the first domain-focused Gold Set; treat repository and framework names as metadata, never research-state evidence.
- Consequences: existing Graph Reconstruction Prompt examples and evaluation fixtures require a separate bias audit before V3 alignment.
- Revisit when: a distinct cross-domain generalization suite is introduced.

### D-005 — 2026-07-28 — Require explicit real-smoke provider activation

- Context: module-level `.env` loading allowed personal BGE-M3, Chroma, and DeepSeek settings to become the effective default configuration.
- Options considered: keep exporting offline variables before every test; stop loading `.env`; introduce explicit runtime profiles while preserving local path configuration.
- Evidence: an isolated config probe observed real Provider selections under the personal `.env`, while explicit offline overrides restored deterministic behavior.
- Decision: default to `offline-dev`, force automated tests to `test` before application imports, and read real Provider selections and credentials only under `real-smoke`.
- Consequences: real Provider validation must use a separate smoke; profile selection does not by itself validate external discovery.
- Revisit when: deployment requires a distinct production configuration contract or a centralized settings system.

### D-006 — 2026-07-31 — Separate deterministic scoring from runtime adapters

- Context: the Gold business routes, structured state, chunk IDs, and grounded-answer contract do not yet match the current V3 runtime types one to one.
- Options considered: silently map the vocabularies; make the evaluator call the current runtime directly; score explicit structured observation artifacts before adding adapters.
- Evidence: V3 `LeaderPlan.plan_type` lacks several Gold routes, Session Summary is still a string, runtime chunks do not expose Gold `chunk_id`, and answers do not expose structured warning or citation fields.
- Decision: make the first evaluator a pure observed-output scorer with strict Gold and observation schemas; add runtime adapters only after each mapping is explicit and tested.
- Consequences: the CI contract probe validates evaluator behavior but is not a runtime or model-quality result.
- Revisit when: V3 exposes stable state, route, chunk identity, and grounded-answer observation contracts.

## Delivered increments

### I-001 — 2026-07-28 — Workflow contract and Gold Scenario v0

- Confirmed scope: design and evaluation artifacts only; no runtime changes.
- Changes:
  - Added [stable workflow and evaluation design](superpowers/specs/2026-07-28-stable-research-workflow-evaluation-design.md).
  - Added [Gold Scenario v0](superpowers/evals/research-agent-gold-v0.json) with 12 synthetic cases.
- Tests executed:
  - JSON parsing with `jq empty`.
  - Unique case IDs and allowed Route checks.
  - Required labels for state, retrieval, answer, and end-to-end scopes.
  - Allowed Citation IDs must exist in each Retrieval Fixture.
  - `git diff --check`.
- Results: all structural checks passed; no model or workflow performance score was produced.
- Known limitations: draft labels require human review; evaluator implementation, Ragas integration, profile isolation, and V3 alignment remain unimplemented.
- Next candidate increment: review and freeze the first development cases, then implement the deterministic evaluator harness.

### I-002 — 2026-07-28 — Correct repository-name domain leakage

- Confirmed scope: revise the new draft artifacts only; do not change historical tests or V3 runtime.
- Changes:
  - Declared that repository and framework names are not research-domain evidence.
  - Changed Gold Scenario v0 primary domain to one-dimensional time-series classification and localization.
  - Reworked cases around sensor shift, short transient events, localization boundary bias, temporal windows, classification precision/recall, and constrained experiments.
  - Bumped the draft dataset to `0.2.0-draft`.
- Tests executed:
  - JSON parsing, unique IDs, allowed Routes, scope labels, and Citation Fixture checks.
  - Search for removed Graph Reconstruction domain terms inside all case payloads.
  - `git diff --check`.
- Results: all structural checks passed; removed domain terms were absent from case payloads.
- Known limitations: the V3 `main` snapshot still contains Graph Reconstruction Planner few-shot and evaluation fixtures that need a separate bias correction when aligning runtime.
- Next candidate increment: user review of time-series scenario realism and missing classification/localization failure modes.

### I-003 — 2026-07-28 — Isolate runtime Provider profiles

- Confirmed scope: configuration isolation and switching only; do not call or stabilize real Providers.
- Changes:
  - Added `test`, `offline-dev`, and `real-smoke` runtime profiles.
  - Added an injectable config loader and offline Provider enforcement.
  - Forced pytest to select `test` before importing application modules.
  - Added profile-switch tests, `.env.example`, and updated offline smoke and Provider documentation.
- Tests executed:
  - Ruff on the changed Python files.
  - 79 focused config and Leader tests.
  - Independent default, test, real-smoke, and invalid-profile process probes.
  - Full backend suite with the repository's existing `PYTHONPATH=backend/src` entry condition.
  - Offline MVP smoke without individual Provider overrides.
- Results: Ruff passed; focused tests passed; profile probes returned the expected configurations; 486 backend tests passed with one existing deprecation warning; offline smoke passed.
- Known limitations: an initial full-test invocation without `PYTHONPATH=backend/src` failed during collection because of the repository's existing import-path convention; no real network Provider smoke was run.
- Next candidate increment: define timeout and typed-failure acceptance for one DeepSeek path, then run its isolated `real-smoke`.

### I-004 — 2026-07-31 — Add the deterministic evaluator harness

- Confirmed scope: implement state, route, retrieval, and answer scoring plus CI integration; do not modify V3 orchestration, call real Providers, add Ragas, or claim a runtime performance result.
- Changes:
  - Added strict Pydantic contracts for Gold scenarios and structured observation artifacts.
  - Added deterministic state, route, retrieval, and answer evaluators with per-case violations and component metric vectors.
  - Added hard gates for labeled state false positives and critical recall, route mismatch, forbidden actions, unknown Chunk IDs, invalid citations, unsupported claims, warning behavior, and Summary-as-evidence violations.
  - Added a JSON CLI and a one-case synthetic `contract_probe` that exercises all four scopes.
  - Added the contract probe to Backend CI and documented the distinction between harness validation and runtime performance.
- Tests executed:
  - Ruff on evaluator code and focused tests.
  - Sixteen evaluator schema, metric, hard-gate, negative-retrieval, missing-observation, and CLI tests.
  - Direct evaluator CLI contract probe under `RUNTIME_PROFILE=test`.
  - Full backend suite under `PYTHONPATH=backend/src RUNTIME_PROFILE=test`.
  - Offline MVP and Agent Team V3 smoke.
  - `git diff --check`.
- Results: all checks passed; 502 backend tests passed with one existing Starlette deprecation warning; offline smoke passed; the contract probe passed its hard gates.
- Known limitations: the Gold set remains `human_review_required`; `performance_claim_valid` is therefore false; no V3 runtime observation adapter, semantic answer judge, ablation, or real Provider score was produced.
- Next candidate increment: define one explicit V3-to-Gold adapter boundary and produce a draft runtime baseline without changing the Gold labels.
