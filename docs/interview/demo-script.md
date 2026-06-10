# Research Management Assistant Demo Script

This script is for interview demos. It focuses on the current implemented MVP and avoids claiming production-grade RAG or fully autonomous agent behavior.

## 1. Demo Goal

Show a local-first Research Management Assistant that helps a researcher move through this workflow:

```text
research query
-> discovery candidates
-> user accept/save
-> PDF upload
-> chunked
-> embedded
-> knowledge retrieval
-> grounded answer
-> structured experiment log
-> idea recommendation
-> memory review
```

The key story is not "one chatbot does everything". The key story is a controlled research workflow where LLMs are used behind explicit boundaries, with deterministic defaults and testable fallback behavior.

## 2. One-Minute Project Pitch

This project is a Research Management Assistant for literature discovery, paper ingestion, knowledge-base retrieval, grounded answering, and experiment-driven idea recommendation.

I built it as a local-first FastAPI + LangGraph + SQLite backend with a Vue Research Workbench frontend. The backend separates external discovery from internal knowledge retrieval: discovery recommends new papers, while knowledge answers only cite embedded local chunks. The paper lifecycle is explicit: discovery candidates are temporary, accepted papers are saved to SQLite, uploaded PDFs are chunked, and embedded papers only become searchable after every chunk has a traceable vector reference.

The system defaults to deterministic/offline providers for reliable testing, but it also supports optional real providers such as DeepSeek for judging/answers and BGE-M3 + Chroma for local embedding/vector storage.

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

Expected smoke marker:

```text
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

## 5. Demo Path A: Research Workbench

Use a query such as:

```text
lightweight interpretable graph reconstruction
```

Explain the two sections:

- Discovery: external candidates from paper discovery workflow.
- Knowledge: local embedded knowledge chunks used for grounded answer.

Important line to say:

> Discovery candidates are recommended readings. They are not answer sources until the user accepts, uploads, chunks, and embeds the paper.

Expected UI checks:

- Backend status shows ok.
- Discovery panel shows current query results.
- Knowledge panel either shows grounded answer/sources or a no-source fallback.
- Partial failures are section-level and should not hide successful sections.

## 6. Demo Path B: Accept And Paper Lifecycle

In Discovery:

1. Pick a candidate.
2. Click Accept.
3. Show it appears in Saved Candidates.

Explain:

```text
discovery candidate -> accepted
```

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

## 7. Demo Path C: Knowledge Retrieval And Grounded Answer

After at least one paper is embedded, use Knowledge search/answer through the workbench or API.

Key explanation:

> Sources are retrieved by the system and passed into the answer generator. The LLM does not invent sources.

If there are no sources, the system should return a fallback instead of forcing an answer.

## 8. Demo Path D: Idea Assistant

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

## 9. Demo Path E: Memory Review

Explain the memory design:

- Structured experiment logs are episodic evidence.
- Memory candidates are review-gated proposals.
- Confirmed semantic memory is only created after user acceptance.
- Stale/conflict automatic handling is future work, not claimed as completed.

Key line:

> This is not raw chat history storage. It is selective, review-gated memory intended to reduce context noise and support future workflows.

## 10. Optional Real Provider Smoke

Only use this if local environment is prepared.

Optional examples:

- `PAPER_JUDGE_PROVIDER=deepseek`
- `ANSWER_PROVIDER=deepseek`
- `EMBEDDING_PROVIDER=bge-m3`
- `VECTOR_BACKEND=chroma`

Do not demo with real providers unless the network, API keys, model cache, and local Chroma directory have already been verified.

## 11. Known Limitations To Say Proactively

- External arXiv/OpenAlex discovery can be affected by network, API, and rate limits.
- Default providers are deterministic/offline, not production AI.
- Idea Assistant default generator is deterministic, not a fully autonomous research agent.
- Memory stale/conflict handling is review-gated/future work.
- PDF parsing does not include OCR or complex layout recovery.
- Frontend is a focused MVP workbench, not a production UI.

## 12. Closing Line

This project demonstrates how I design agentic systems as controllable workflows: deterministic defaults for testability, optional real providers for capability, explicit state transitions, evidence boundaries, and user-reviewed persistence.
