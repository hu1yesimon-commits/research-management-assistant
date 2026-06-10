# Backend E2E Demo And Smoke

> This document is a demo and smoke guide only. It does not claim new product behavior beyond what is already implemented in the backend.

## Goal

Provide one place to demo and smoke-check the current MVP end to end without adding new business logic.

Current implemented demo surfaces include:

- Research Workbench frontend
- Idea Assistant MVP
- Memory System MVP

This guide covers four paths:

- `A. Offline deterministic path`
- `B. Research Workbench interview path`
- `C. Real local ingestion path`
- `D. Real LLM answer provider manual smoke`

Default paths remain local/offline:

- no streaming or SSE
- no multi-turn chat
- default tests still do not require real LLM answer generation
- default smoke does not require BGE-M3, Chroma, DeepSeek/OpenAI, arXiv/OpenAlex, or network access

## Key Boundaries

Current system boundaries that matter during demos:

- Research Workbench is implemented as a Vue 3 + Vite MVP and talks to the FastAPI backend
- `/search` paper discovery and knowledge retrieval are still two different chains
- `/research/query` is the current best candidate for a frontend-facing unified entrypoint because it can return discovery and knowledge in one response
- `/research/query` returns two sections: `discovery` and `knowledge`
- discovery candidates are not grounded answer sources; they must not be interpreted as `knowledge.sources`
- `/knowledge/search` and `/knowledge/answer` operate on already embedded knowledge chunks
- `/knowledge/answer` defaults to a deterministic grounded answer; real LLM answer generation is optional manual smoke only
- `/experiments/logs` and `/ideas/recommend` are implemented for the Idea Assistant MVP
- `/memory/candidates/*` and `/memory/semantic/*` are implemented for the Memory System MVP
- stale/conflict automatic detection or automatic mutation is future work; current Memory System behavior is review-gated and explicit
- OpenAlex enrichment is best-effort; missing nested fields should degrade candidate enrichment instead of failing the whole discovery workflow
- external API HTTP or network failures can still produce partial failures or missing enrichment data
- retrieval uses `distance`, and smaller `distance` means a more relevant hit
- first real BGE-M3 run may download model files

## Path A: Offline Deterministic Path

### Purpose

Use this path for:

- fast local regression
- API contract checks
- deterministic backend demo without model downloads
- confidence that retrieval and grounded answer orchestration still work

### Runtime Mode

Use default offline-friendly configuration:

- `EMBEDDING_PROVIDER=fake`
- `VECTOR_BACKEND=fake`

### What This Path Verifies

- paper can move through `uploaded -> chunked -> embedded`
- retrieval can return embedded chunks through `/knowledge/search`
- grounded answer can return deterministic answer plus sources through `/knowledge/answer`
- structured experiment logs can be saved through `/experiments/logs`
- memory candidates can be refreshed through `/memory/candidates/refresh`
- Idea Assistant can return deterministic ideas through `/ideas/recommend`
- Idea Assistant evidence can come from retrieval chunks rather than invented citations
- API shapes and SQLite-backed state transitions are intact

### Recommended Demo Sequence

1. Run backend tests:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
```

2. Start the backend with default config:

```bash
PYTHONPATH=backend/src ./.venv/bin/uvicorn main:app --app-dir backend/src --port 8000
```

3. In another terminal, run quick health checks:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/memory/summary
```

4. Run the default offline HTTP smoke:

```bash
bash backend/scripts/smoke_offline_mvp.sh
```

This script uses temporary SQLite state plus in-process FastAPI HTTP requests. It does not bind a port, does not write repo runtime data, and does not use real providers or network.

5. Use deterministic API tests as the broader backend smoke:

- `POST /papers/{paper_id}/embed`
- `POST /knowledge/search`
- `POST /knowledge/answer`
- `POST /experiments/logs`
- `POST /memory/candidates/refresh`
- `POST /ideas/recommend`

Recommended verification command:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest \
  backend/src/tests/test_api_mvp.py \
  backend/src/tests/test_retrieval_service.py \
  backend/src/tests/test_qa_service.py \
  -q
```

### Coverage Summary

This path covers these endpoints:

- `GET /health`
- `POST /research/query`
- `POST /logs`
- `GET /logs`
- `POST /experiments/logs`
- `GET /experiments/logs`
- `POST /memory/candidates/refresh`
- `GET /memory/candidates`
- `POST /memory/candidates/{candidate_id}/accept`
- `GET /memory/semantic`
- `POST /ideas/recommend`
- `POST /papers/{paper_id}/embed`
- `POST /knowledge/search`
- `POST /knowledge/answer`

### Automation Level

Automatic smoke:

- `backend/scripts/smoke_offline_mvp.sh`
- pytest-based API and service tests

Manual steps:

- optional `uvicorn` startup
- optional curl inspection of responses

### Unified Research Query Smoke

Use this smoke when you want one backend call that exercises both user-facing sections.

Recommended requests:

1. Discovery only:

```bash
curl -sS -X POST http://127.0.0.1:8000/research/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"lightweight graph reconstruction","mode":"basic","include_discovery":true,"include_knowledge":false,"top_k":5}'
```

2. Discovery plus knowledge:

```bash
curl -sS -X POST http://127.0.0.1:8000/research/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"lightweight graph reconstruction","mode":"basic","include_discovery":true,"include_knowledge":true,"top_k":5}'
```

Expected interpretation:

- `discovery.enabled` and `knowledge.enabled` reflect the requested sections
- `discovery.candidates` contains paper candidates only
- `knowledge.sources` contains grounded retrieval chunks only
- discovery must not fail with `NoneType.get` just because OpenAlex returns incomplete nested fields
- when OpenAlex enrichment is incomplete, candidate papers should still be returned with partial metadata and raw/debug traces where available
- if an upstream API returns HTTP failures or network errors, the response may still show section-level partial failure instead of complete success

## Path B: Research Workbench Interview Path

### Purpose

Use this path when showing the product surface rather than only backend contracts.

### Start Backend

```bash
PYTHONPATH=backend/src ./.venv/bin/uvicorn main:app --app-dir backend/src --port 8000
```

### Start Frontend

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

### Recommended UI Sequence

1. Open the Research Workbench.
2. Submit a research query.
3. Explain that `discovery` and `knowledge` are independent sections from `/research/query`.
4. Accept one discovery candidate.
5. Upload a PDF for the saved candidate.
6. Use `Embed / Advance Status` to move `uploaded -> chunked -> embedded`.
7. Submit an Idea Assistant structured experiment log.
8. Explain that Idea Assistant recommendations are deterministic by default and that any `supporting_evidence` comes from retrieval/discovery payloads.
9. For Memory System MVP, use backend smoke or curl to show `POST /memory/candidates/refresh`, then accept/reject candidate review.

### Frontend Verification

```bash
cd frontend
npm test
npm run build
```

### Explicit Limitations

- The current Workbench is an engineering MVP, not a production UI.
- There is no dedicated Memory System review panel yet; memory review is currently backend/API-driven.
- Browser/dev-server validation can be environment-sensitive in sandboxes; component tests and build are the default automated verification.

## Path C: Real Local Ingestion Path

### Purpose

Use this path for:

- local validation of the optional real embedding/vector path
- proving `chunked -> embedded` works with BGE-M3 plus Chroma
- checking retrieval and grounded answer on top of real locally stored vectors

### Runtime Mode

Use real local integration settings:

- `EMBEDDING_PROVIDER=bge-m3`
- `VECTOR_BACKEND=chroma`
- clean SQLite database path
- clean Chroma persist dir

### What This Path Verifies

- real BGE-M3 embeddings can be generated locally
- Chroma can persist vectors to a local persist dir
- `embedded` is only reached after all chunks have non-empty `vector_ref`
- retrieval can query the persisted vectors
- grounded answer can build deterministic answers from retrieved sources

### Existing Automated Piece

The current real embedding smoke script is:

- [backend/scripts/smoke_embed_bge_chroma.sh](/Users/nuonuohu/Developer/graphReconstruction/backend/scripts/smoke_embed_bge_chroma.sh)

What it already automates:

- create clean temp SQLite and Chroma paths
- set:
  - `EMBEDDING_PROVIDER=bge-m3`
  - `VECTOR_BACKEND=chroma`
  - `BGE_M3_MODEL_NAME=BAAI/bge-m3`
  - `CHROMA_COLLECTION_NAME=research_chunks`
- seed one chunked paper
- call `POST /papers/{paper_id}/embed`
- verify:
  - embedded response
  - SQLite `vector_ref` presence
  - Chroma ids exist

### Run The Existing Real Embed Smoke

```bash
cd /Users/nuonuohu/Developer/graphReconstruction
bash backend/scripts/smoke_embed_bge_chroma.sh
```

Expected key output:

- `EMBED_RESPONSE={"paper_id":"smoke-paper-1","status":"embedded","vector_ref_count":2}`
- `SQLITE_VECTOR_REF_COUNT=2`
- `SQLITE_VECTOR_REFS_OK=true`
- `CHROMA_ID_COUNT=2`
- `CHROMA_WRITE_OK=true`

### Manual Retrieval And Answer Follow-Up

After confirming the real embed smoke, use the same configuration style to run the backend and manually verify:

1. `POST /knowledge/search`
2. `POST /knowledge/answer`

Recommended setup:

- keep a clean SQLite database path
- keep a clean Chroma persist dir
- start `uvicorn` with:
  - `EMBEDDING_PROVIDER=bge-m3`
  - `VECTOR_BACKEND=chroma`
  - `BGE_M3_MODEL_NAME=BAAI/bge-m3`
  - `CHROMA_COLLECTION_NAME=research_chunks`

Recommended manual sequence:

1. Seed or retain at least one `embedded` paper with chunks in SQLite and vectors in Chroma
2. Call:

```bash
curl -sS -X POST http://127.0.0.1:8000/knowledge/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"graph reconstruction","top_k":5}'
```

3. Then call:

```bash
curl -sS -X POST http://127.0.0.1:8000/knowledge/answer \
  -H 'Content-Type: application/json' \
  -d '{"question":"How should I approach graph reconstruction?","top_k":5}'
```

Expected interpretation:

- `/knowledge/search` returns chunk hits with `distance`
- smaller `distance` means more relevant chunks
- `/knowledge/answer` returns grounded answer plus `sources`
- with default `ANSWER_PROVIDER=deterministic`, the answer is not a real LLM answer

### Automation Level

Automatic smoke:

- `backend/scripts/smoke_embed_bge_chroma.sh` for the real `chunked -> embedded` path

Manual steps:

- manually keep the backend running after embedding if you want to test retrieval and answer
- manually call `/knowledge/search`
- manually call `/knowledge/answer`

## Path D: Real LLM Answer Provider Manual Smoke

### Purpose

Use this path only for an explicit manual smoke of the optional real answer provider.

This path is for:

- confirming the backend can switch `/knowledge/answer` from deterministic mode to a real LLM provider
- checking that answer generation still stays grounded on retrieval sources
- verifying provider wiring without changing default pytest behavior

This path is not for:

- default regression testing
- CI
- production-grade answer quality validation

### Preconditions

Run this path only after all of the following are already true:

- at least one paper is already in `embedded` status
- `POST /knowledge/search` can already retrieve non-empty chunks for the target question domain
- local environment variables for the real LLM provider have been set
- network access and a valid API key are available on the local machine

### Supported Real Answer Providers

Current real LLM answer smoke can be run with:

- `ANSWER_PROVIDER=openai`
- `ANSWER_PROVIDER=deepseek`

DeepSeek is supported for real `/knowledge/answer` and `/research/query` knowledge-section manual smoke when the local environment provides valid provider configuration.

If `/knowledge/search` is empty, stop here first. The no-source path is expected to return:

- `No relevant knowledge chunks were found.`

And in that no-source case, the backend should not call the real LLM provider.

### Environment Variables

Example local environment setup:

```bash
export ANSWER_PROVIDER=openai
export ANSWER_MODEL=gpt-4.1-mini
export ANSWER_TEMPERATURE=0
export OPENAI_API_KEY=your_key_is_read_from_local_env
```

Notes:

- do not commit any real API key
- do not place a real API key in README examples, test data, or repo scripts
- `OPENAI_API_KEY` must come from local environment only

### Start Command

Start the backend with the real provider environment already loaded:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m uvicorn main:app --reload
```

### Recommended Manual Sequence

1. Confirm retrieval is non-empty before testing answer generation:

```bash
curl -sS -X POST http://127.0.0.1:8000/knowledge/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"graph reconstruction","top_k":5}'
```

2. Then smoke `POST /knowledge/answer`:

```bash
curl -sS -X POST http://127.0.0.1:8000/knowledge/answer \
  -H 'Content-Type: application/json' \
  -d '{"question":"How should I approach graph reconstruction?","top_k":5}'
```

### What To Verify

Expected verification points:

- response contains `answer`
- response contains non-empty `sources`
- `mode` is `llm` or the provider-specific non-deterministic mode value exposed by the backend
- `sources` still come from retrieval results rather than being invented by the model
- if retrieval has no sources, the backend should return the no-source fallback instead of calling the provider

Practical interpretation:

- the answer text may vary across runs
- the `sources` payload should still map to retrieved chunk metadata such as `paper_id`, `chunk_index`, `text`, and `vector_ref`
- successful smoke proves provider wiring and grounding flow, not answer excellence

### Explicit Limitations

This manual smoke has important limits:

- it is not part of default pytest
- it depends on network access and a valid API key
- it does not guarantee answer quality equal to a production RAG system
- it does not include streaming or SSE
- it does not include multi-turn chat memory
- it does not change `/search` paper discovery behavior
- it does not prove end-to-end production hardening, retries, or evaluation quality

## Demo Path Summary

Fast offline backend demo:

1. run pytest
2. run `backend/scripts/smoke_offline_mvp.sh`
3. optionally start `uvicorn`
4. show `POST /knowledge/search`
5. show `POST /knowledge/answer`

Research Workbench demo:

1. start backend
2. start frontend
3. submit query
4. accept discovery candidate
5. upload and embed PDF
6. submit Idea Assistant log
7. review memory candidates through backend smoke/curl

Real local integration demo:

1. run `backend/scripts/smoke_embed_bge_chroma.sh`
2. confirm `chunked -> embedded`
3. run backend with `bge-m3 + chroma`
4. call `/knowledge/search`
5. call `/knowledge/answer`

Real LLM answer provider demo:

1. confirm an `embedded` paper already exists
2. confirm `/knowledge/search` returns non-empty chunks
3. export `ANSWER_PROVIDER=openai`, `ANSWER_MODEL`, `ANSWER_TEMPERATURE`, and local `OPENAI_API_KEY`
4. start `uvicorn` with `PYTHONPATH=backend/src ./.venv/bin/python -m uvicorn main:app --reload`
5. call `/knowledge/answer`
6. verify `answer`, non-empty `sources`, and `mode=llm` or equivalent non-deterministic mode

## What The Current Backend Loop Still Lacks

Even after these demo paths, the backend is still not a full RAG product.

Still missing:

- `/search` to retrieval handoff
- multi-turn QA memory
- streaming / SSE
- stale/conflict automatic memory handling
- Memory System frontend review UI

Still not guaranteed by this smoke:

- production-grade grounded answer quality
- robust online evaluation or prompt tuning
- automatic regression coverage for real provider calls
- frontend UI
- production-grade prompt orchestration
- citation formatting beyond source passthrough
