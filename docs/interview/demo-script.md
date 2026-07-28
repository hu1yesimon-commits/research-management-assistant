# Research Management Assistant Demo Script

This script is for interview demos. It focuses on the current implemented MVP and avoids claiming production-grade RAG or fully autonomous agent behavior.

## 1. Demo Goal

Show a local-first Research Management Assistant that helps a researcher move through this workflow:

```text
default session chat
-> active candidates
-> user accept/save
-> saved papers
-> PDF upload
-> chunked
-> embedded
-> grounded answer
-> structured experiment log
-> idea recommendation
-> memory review
```

The key story is not "one chatbot does everything". The key story is a controlled research workflow where LLMs are used behind explicit boundaries, with deterministic defaults and testable fallback behavior.

## 2. One-Minute Project Pitch

This project is a Research Management Assistant for literature discovery, paper ingestion, knowledge-base retrieval, grounded answering, and experiment-driven idea recommendation.

I built it as a local-first FastAPI + LangGraph + SQLite backend with a Vue Research Workbench frontend. The current primary path is a default permanent Session that runs a bounded synchronous `Leader + Research + Idea` workflow. The backend separates external discovery from internal knowledge retrieval: discovery recommends new papers, while knowledge answers only cite embedded local chunks. The paper lifecycle is explicit: session active candidates are temporary, accepted papers are saved to SQLite, uploaded PDFs are chunked, and embedded papers only become searchable after every chunk has a traceable vector reference.

The system defaults to deterministic/offline providers for reliable testing, but it also supports optional real providers such as DeepSeek for judging/answers and BGE-M3 + Chroma for local embedding/vector storage.

`POST /sessions/default/turns` is the Agent Team V3 entrypoint. It returns the assistant message, a typed plan, active candidates, bounded agent-run summaries, typed errors, and any grounded knowledge or idea payloads. `POST /research/assistant` still exists as a compatibility surface during migration.

## 3. Before Demo

From the project root:

```bash
cd /Users/nuonuohu/Developer/graphReconstruction
```

Run backend tests:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
```

Run frontend checks:

```bash
cd frontend
npm test
npm run build
cd ..
```

Run offline smoke:

```bash
bash backend/scripts/smoke_offline_mvp.sh
```

Expected smoke markers:

```text
AGENT_TEAM_V3_SMOKE_OK=true
OFFLINE_MVP_SMOKE_OK=true
```

## 4. Start Services

Start backend:

```bash
cd /Users/nuonuohu/Developer/graphReconstruction
PYTHONPATH=backend/src ./.venv/bin/python -m uvicorn main:app --reload
```

Start frontend in another terminal:

```bash
cd /Users/nuonuohu/Developer/graphReconstruction/frontend
npm run dev -- --host 127.0.0.1
```

Open:

```text
http://127.0.0.1:5173
```

## 5. Demo Path A: Default Session Chat

Start in the default Session chat and ask:

```text
Find recent papers about graph reconstruction
```

Show:

- the persistent user/assistant chat history
- the Active Candidates panel
- the Agent Trace panel with a bounded typed plan

Important line to say:

> The main path is a single default Session. This is logical persistence in SQLite, not a resident background agent process.

## 6. Demo Path B: Accept And Paper Lifecycle

In Active Candidates:

1. Pick a candidate.
2. Click Accept.
3. Show it disappears from the active session batch and appears in Saved Papers.

Explain:

```text
active candidate -> accepted saved paper
```

Also explain the boundary:

> Active Candidates are temporary session-level recommendations. Saved Papers are the global persistent library. Confirmed Memory is a separate review-gated long-term layer.

Then upload a local PDF if available:

```text
accepted -> uploaded
```

Then click Embed / Advance Status:

```text
uploaded -> chunked -> embedded
```

Explain:

- `chunked` means PDF text extraction and chunk persistence succeeded.
- `embedded` means every target chunk has a non-empty vector reference.
- SQLite stores chunk text and vector references for debuggability.

## 7. Demo Path C: Grounded Answer And Trace

After the session turn completes, open Agent Trace.

Explain:

- the Leader produces a typed bounded plan
- Research owns fresh discovery
- Idea only runs when experiment context and coverage are appropriate
- traces show bounded run outcomes, not raw prompts or internal chain-of-thought

If knowledge is present, use the answer panel to explain:

Key explanation:

> Sources are retrieved by the system and passed into the answer generator. The LLM does not invent sources.

If there are no sources, the system should return a fallback instead of forcing an answer.

## 8. Demo Path D: Legacy Tools Compatibility

Open the collapsed `Legacy tools` section.

Explain:

- direct `POST /research/query` and the standalone Idea Assistant are still available during the migration window
- they are not the primary product path anymore
- `POST /research/assistant` remains for V1 compatibility, not because the product supports two equal orchestration models

## 9. Demo Path E: Idea Assistant

Submit a structured experiment log, for example:

```text
Task: defect classification
Model: 1D-CNN
Metric/problem: minority class PRAUC is low
Tried methods: class weighting, focal loss
Goal: improve PRAUC without making the model too heavy
```

Show idea options.

Explain:

- Idea Assistant is driven by user-submitted structured logs.
- It retrieves supporting evidence from local knowledge.
- Each idea should include rationale, evidence, risk, expected benefit, validation metric, and next experiment.
- Default provider is deterministic/offline for testability.

## 10. Demo Path F: Memory Review

Explain the memory design:

- Structured experiment logs are episodic evidence.
- Memory candidates are review-gated proposals.
- Confirmed semantic memory is only created after user acceptance.
- Stale/conflict automatic handling is future work, not claimed as completed.

Key line:

> This is not raw chat history storage. It is selective, review-gated memory intended to reduce context noise and support future workflows.

## 11. Optional Real Provider Smoke

Only use this if local environment is prepared.

Optional examples:

- `PAPER_JUDGE_PROVIDER=deepseek`
- `ANSWER_PROVIDER=deepseek`
- `EMBEDDING_PROVIDER=bge-m3`
- `VECTOR_BACKEND=chroma`

Do not demo with real providers unless the network, API keys, model cache, and local Chroma directory have already been verified.

## 12. Known Limitations To Say Proactively

- External arXiv/OpenAlex discovery can be affected by network, API, and rate limits.
- Current session path is one default permanent Session; there is no multi-session UI yet.
- The Agent Team is bounded and synchronous; there is no free-loop autonomy or resident mailbox worker.
- Default providers are deterministic/offline, not production AI.
- Idea Assistant default generator is deterministic, not a fully autonomous research agent.
- Memory stale/conflict handling is review-gated/future work.
- PDF parsing does not include OCR or complex layout recovery.
- Frontend is a focused MVP workbench, not a production UI.

## 13. Closing Line

This project demonstrates how I design agentic systems as controllable workflows: deterministic defaults for testability, optional real providers for capability, explicit state transitions, evidence boundaries, and user-reviewed persistence.
