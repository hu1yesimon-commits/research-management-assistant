# Backend E2E Demo And Smoke

> This document is a demo and smoke guide only. It does not claim new product behavior beyond what is already implemented in the backend.

## Goal

Provide one place to demo and smoke-check the current backend MVP end to end without adding new business logic.

This guide covers two paths:

- `A. Offline deterministic path`
- `B. Real local ingestion path`
- `C. Real LLM answer provider manual smoke`

Both paths are backend-only:

- no frontend
- no streaming or SSE
- no multi-turn chat
- default tests still do not require real LLM answer generation

## Key Boundaries

Current system boundaries that matter during demos:

- `/search` paper discovery and knowledge retrieval are still two different chains
- `/knowledge/search` and `/knowledge/answer` operate on already embedded knowledge chunks
- `/knowledge/answer` defaults to a deterministic grounded answer; real LLM answer generation is optional manual smoke only
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

4. Use deterministic API tests as the main smoke:

- `POST /papers/{paper_id}/embed`
- `POST /knowledge/search`
- `POST /knowledge/answer`

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
- `POST /logs`
- `GET /logs`
- `POST /papers/{paper_id}/embed`
- `POST /knowledge/search`
- `POST /knowledge/answer`

### Automation Level

Automatic smoke:

- pytest-based API and service tests

Manual steps:

- optional `uvicorn` startup
- optional curl inspection of responses

## Path B: Real Local Ingestion Path

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

- [backend/scripts/smoke_embed_bge_chroma.sh](/Users/nuonuohu/Developer/graphReconstruction-phase-2d-v2/backend/scripts/smoke_embed_bge_chroma.sh)

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
cd /Users/nuonuohu/Developer/graphReconstruction-phase-2d-v2
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
- `/knowledge/answer` returns deterministic grounded answer plus `sources`
- answer is not a real LLM answer

### Automation Level

Automatic smoke:

- `backend/scripts/smoke_embed_bge_chroma.sh` for the real `chunked -> embedded` path

Manual steps:

- manually keep the backend running after embedding if you want to test retrieval and answer
- manually call `/knowledge/search`
- manually call `/knowledge/answer`

## Path C: Real LLM Answer Provider Manual Smoke

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
2. optionally start `uvicorn`
3. show `POST /knowledge/search`
4. show `POST /knowledge/answer`

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
- unified research workflow across discovery and knowledge retrieval
- multi-turn QA memory
- streaming / SSE

Still not guaranteed by this smoke:

- production-grade grounded answer quality
- robust online evaluation or prompt tuning
- automatic regression coverage for real provider calls
- frontend UI
- production-grade prompt orchestration
- citation formatting beyond source passthrough
