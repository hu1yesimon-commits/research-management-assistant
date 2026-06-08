# Phase 2D Real Embedding And Vector Ref Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define a strict Phase 2D plan that promotes papers from `chunked` to `embedded` only after real embeddings are written and every persisted chunk has a traceable `vector_ref`.

**Architecture:** Phase 2D builds on the current Phase 2C pipeline instead of replacing it. `chunked` remains the boundary for “PDF text extracted and chunks persisted”, while Phase 2D adds a separate embedding-and-vector-write phase that reads existing `knowledge_chunks`, writes vectors through a thin vector-store service, stores traceable `vector_ref` values back into SQLite, and only then updates the paper to `embedded`.

**Tech Stack:** Existing FastAPI service, existing SQLite `MemoryStore`, existing `knowledge_chunks` table, future embedding provider abstraction, future vector-store abstraction, Chroma as the selected Phase 2D vector backend, no real implementation in this plan.

---

## Scope

This plan covers:

- why Chroma is the selected backend instead of FAISS for this project phase
- `vector_ref` write-back design for `knowledge_chunks`
- `page_number` as a future extension point rather than a Phase 2D requirement
- future chunk-parameter configuration guidance for PDF ingestion
- `chunked -> embedded` status flow
- failure semantics that keep papers in `chunked` when embedding fails
- test strategy for service, store, and API layers
- implementation sequencing for a future Phase 2D execution pass

This plan explicitly does **not** include:

- real embedding provider integration
- real Chroma integration
- real FAISS integration
- retrieval, RAG, search, judge, or rank changes
- `page_number` extraction as a required Phase 2D output
- OCR, parser upgrades, or chunking-policy redesign

## Current Baseline

What is already true in the repo today:

- `PaperStatus` includes `uploaded`, `chunked`, and `embedded`.
- `POST /papers/{paper_id}/embed` currently implements Phase 2C behavior only.
- Phase 2C starts from `uploaded`, extracts text, writes `knowledge_chunks`, and updates the paper to `chunked`.
- `knowledge_chunks.vector_ref` exists but remains nullable and unused in current runtime behavior.
- No current path should mark a paper `embedded` as part of Phase 2C.

Phase 2D should preserve all of that and add a separate strict meaning:

- `chunked` = chunk persistence completed
- `embedded` = real embedding completed for all target chunks, and every embedded chunk has a non-null traceable `vector_ref`

## State Semantics

Required lifecycle for Phase 2D:

`uploaded -> chunked -> embedded`

State meanings:

- `uploaded` = local PDF file exists and `pdf_path` is recorded, but chunk persistence is not yet guaranteed
- `chunked` = PDF text extraction succeeded and chunk rows were written into `knowledge_chunks`
- `embedded` = every chunk selected for embedding has completed real embedding, the vector backend has accepted the vectors, and every embedded chunk row has a non-empty traceable `vector_ref`

Strict rules:

- Phase 2D must start from `chunked`, not `uploaded`
- Phase 2D must never skip directly from `uploaded` to `embedded`
- embedding failure must leave the paper in `chunked`
- partial vector writes must not cause the paper to become `embedded`
- if any target chunk is missing `vector_ref`, the paper must remain `chunked`

## Vector Store Choice

Phase 2D now has a project-level conclusion: use **Chroma** as the vector backend for the first real embedding phase. The reason is not “Chroma is universally best”, but “Chroma is the best fit for this repo’s current MVP priorities”.

### Option A: Chroma

Strengths:

- simpler developer ergonomics for local MVP iteration
- document-oriented API surface is easier to wire to chunk records
- easier metadata association per chunk for a first real embedding phase
- lower cognitive overhead when debugging small local datasets

Risks:

- more project-specific API coupling if used directly from endpoint code
- persistence layout is more opaque than a plainly managed index directory
- later migration away from Chroma can be noisier if abstraction is weak

Better fit when:

- the main goal is getting a local end-to-end research assistant working quickly
- inspectability of metadata and developer convenience matter more than index-control purity
- the team expects small-to-medium local corpora first

### Option B: FAISS

Strengths:

- lighter-weight core vector index
- more explicit control over on-disk index files
- simpler mental model if the team wants vector indexing to stay as infrastructure, not as a document store

Risks:

- metadata mapping is more manual, so the app must own more bookkeeping
- `vector_ref` traceability design becomes more important because FAISS does not give the same document-store ergonomics
- local MVP wiring usually takes more surrounding code than Chroma

Better fit when:

- the team prefers explicit file-managed infrastructure
- metadata and vector-id mapping being app-owned is acceptable
- long-term backend control matters more than first-pass ergonomics

### Final Project Conclusion

Current project decision:

- Phase 2D will use **Chroma**

Why this is the chosen conclusion:

- Phase 2D’s main risk is integration correctness, not index-theory optimization
- the team needs to stabilize `chunked -> embedded`, `vector_ref` write-back, and failure semantics before optimizing lower-level index control
- Chroma gives a cleaner local MVP path for chunk metadata association and end-to-end debugging
- FAISS remains a valid future reevaluation option, but it is not a Phase 2D target for the current project line

Architectural constraint regardless of choice:

- do not let `main.py` or route handlers depend directly on Chroma or FAISS APIs
- hide backend-specific details behind a dedicated vector-store service boundary
- make `vector_ref` format backend-specific but contract-stable at the application layer

## `vector_ref` Design

Phase 2D should treat `vector_ref` as the app-visible receipt proving that a specific chunk has been embedded into a specific backend.

Required properties:

- traceable: given one `vector_ref`, engineers can locate the corresponding vector entry
- stable enough for debugging and rebuilds
- backend-aware without leaking too much backend-specific logic across the app
- one stored value per embedded chunk row

Recommended shape:

- store `vector_ref` as a string
- encode both backend identity and backend-local record identity
- keep the format simple and parseable
- treat the value as an app-visible receipt proving the chunk was written into the vector backend

Recommended example:

- Chroma-style: `chroma:<collection_name>:<chunk_uid>`

Recommended chunk identity rule:

- derive a stable app-level chunk uid from `paper_id`, `chunk_index`, and `chunk_hash`
- use that uid when writing vectors so rebuild and overwrite behavior stays debuggable

Recommended persistence rule:

- `vector_ref` is written only after the vector backend confirms the write
- if vector write fails for a chunk, its `vector_ref` remains null or is rolled back
- the paper status remains `chunked` until all target chunks have non-null traceable `vector_ref`
- `vector_ref` should never be treated as optional once a paper is considered `embedded`

## `page_number` Extension

`page_number` has clear future value for quote tracing, citation support, and user-facing source navigation, but it should not be treated as a required Phase 2D deliverable.

Recommended project position:

- `page_number` is valuable for future reference traceability
- `page_number` is not a must-have for Phase 2D real embedding
- add it later as part of Phase 2E or a PDF extraction quality upgrade

Recommended schema direction if it is added later:

- add nullable `page_number` to `knowledge_chunks`
- write the same `page_number` into Chroma metadata for the corresponding chunk

Reason for deferring:

- page attribution quality depends on extraction fidelity, not only embedding flow correctness
- forcing it into Phase 2D would mix retrieval-traceability work with the core embedding-state transition goal

## Dependencies, Provider, And Local Persistence

Phase 2D needs to make three infrastructure decisions explicit in the plan: dependency direction, default embedding-provider direction, and local persistence layout.

### Dependencies

Phase 2D dependency direction should be:

- add `chromadb` as the planned vector-store dependency for the Chroma backend
- add an embedding-provider dependency path, but do not hard-bind Phase 2D to OpenAI embeddings
- treat `langchain-openai` as already present in the repo, but not as the default Phase 2D embedding path

Recommended implementation boundary:

- prioritize a thin in-project `EmbeddingService` abstraction first
- let provider-specific packages sit behind that abstraction
- avoid writing provider SDK assumptions directly into route handlers or generic business logic

Confirmed default direction for this project:

- default embedding provider direction is **BGE-M3**
- default model direction is `BAAI/bge-m3`

Important planning constraint:

- this plan does **not** claim that `chromadb`, BGE-M3, a local model runtime, or any remote embedding service is already installed or implemented

### Embedding Provider

Recommended default provider for Phase 2D:

- `bge-m3`

Recommended configuration:

- `EMBEDDING_PROVIDER=bge-m3`
- `EMBEDDING_MODEL=BAAI/bge-m3`

Recommended service boundary:

- wrap provider behavior behind `EmbeddingService`
- keep a stable app-facing interface such as `embed_texts(texts: list[str]) -> list[list[float]]`

Testing rule:

- tests must use a fake embedding provider
- tests must not call real BGE-M3, a local model runtime, OpenAI embeddings, or any remote API
- if there is no model file, no GPU, no API key, and no external service, the default test suite must still pass

Why BGE-M3 is the current default direction:

- it is a good fit for Chinese-English mixed research text
- it is aligned with retrieval and embedding use cases
- it better matches this project’s combination of research-paper content and Chinese-speaking user workflows
- it preserves future flexibility because it can later be used through local deployment or a compatible service layer

Provider fallback note:

- OpenAI embeddings can remain a future alternative provider
- OpenAI embeddings are **not** the default provider choice for Phase 2D

### BGE-M3 Integration Boundary

The plan should not lock Phase 2D to one concrete runtime style for BGE-M3.

Future implementation may follow either of these routes:

- local model route: load `BAAI/bge-m3` locally through `sentence-transformers` or HuggingFace
- service route: call an internal or third-party embedding API service that exposes BGE-M3-compatible embeddings

Required architectural rule:

- both routes must be hidden behind `EmbeddingService`
- `main.py` must not directly depend on BGE-M3, `sentence-transformers`, HuggingFace, OpenAI SDKs, or any provider-specific client

### Chroma Vector Store

Phase 2D vector backend direction is:

- use `chromadb` as the planned Chroma dependency
- use Chroma as the Phase 2D vector backend

Recommended service boundary:

- wrap Chroma access behind `VectorStoreService`
- do not let `main.py` depend directly on Chroma APIs

Recommended configuration:

- `CHROMA_PERSIST_DIR=backend/data/vector_store/chroma`
- `CHROMA_COLLECTION_NAME=research_chunks`

Recommended app-facing interface:

- `upsert_chunks(chunks, embeddings) -> list[str]`

Return-contract rule:

- the returned `list[str]` should be the `vector_ref` list for the upserted chunks

### `vector_ref` Receipt Contract

Phase 2D should continue to use:

- `chroma:<collection_name>:<chunk_uid>`

Chunk identity rule:

- `chunk_uid` should be derived from `paper_id`, `chunk_index`, and `chunk_hash`

Promotion rule:

- before a paper enters `embedded`, every target chunk must have a non-empty `vector_ref`
- if any target chunk lacks `vector_ref`, the paper must remain `chunked`

### Local Persistence

Phase 2D local persistence should be split by responsibility:

- SQLite continues to store `knowledge_chunks` and `vector_ref`
- Chroma persists local vector data under `CHROMA_PERSIST_DIR`

Planned local persistence directory:

- `backend/data/vector_store/chroma`

Important documentation note for later README work:

- `backend/data` is local runtime data
- real user PDFs, SQLite databases, Chroma data, and local model caches should not be committed to git

If the project later adopts a local BGE-M3 runtime:

- local model cache directories should also be treated as non-committed runtime artifacts

## Chunk Parameter Configuration

Current Phase 2C chunking uses character-window splitting. Phase 2D does not need to redesign that policy, but the plan should reserve a cleaner configuration path.

Recommended future configuration surface:

- `PDF_CHUNK_SIZE=3000`
- `PDF_CHUNK_OVERLAP=400`

How to interpret these values:

- they are initial empirical defaults for research-paper PDFs
- they are not presented as globally optimal settings
- they should remain configurable because extraction style, document density, and later retrieval quality work may change them

Future direction if the project later adopts a token-based splitter:

- recommended starting range: `800-1200` tokens
- recommended overlap range: `100-200` tokens

Important boundary:

- Phase 2D should consume persisted chunks and vectorize them
- chunk-policy redesign remains a later tuning step, not a prerequisite for real embedding

## Write-Back Strategy

Phase 2D should read already persisted chunks rather than rebuilding them.

Recommended runtime sequence:

1. Load paper by `paper_id`
2. Verify paper exists
3. Verify paper status is exactly `chunked`
4. Load `knowledge_chunks` for the paper
5. Verify chunk rows exist
6. Build embedding input from persisted chunk text
7. Send vectors to the configured embedding provider and vector backend through service boundaries
8. Receive backend-local identifiers
9. Write `vector_ref` back to each chunk row
10. Verify all required chunk rows now have traceable `vector_ref`
11. Update paper status to `embedded`

Required sequencing constraint:

- paper status update happens last

Recommended atomicity rule:

- if the implementation cannot make vector write plus SQLite write fully transactional across systems, the code should still make “paper becomes embedded” the final gated step after verification

## Failure Handling

Phase 2D should distinguish at least these cases:

- `404`: paper does not exist
- `400`: paper is not `chunked`
- `400` or `409`: no chunk rows exist for a supposedly `chunked` paper
- `422` or `500`: embedding generation failed
- `422` or `500`: vector backend write failed
- `500`: chunk rows were embedded externally but `vector_ref` write-back failed locally

State rules:

- if embedding generation fails, keep paper in `chunked`
- if vector backend write fails, keep paper in `chunked`
- if some chunks succeed and some fail, keep paper in `chunked`
- never mark the paper `embedded` while any target chunk is missing a valid `vector_ref`
- never mark the paper `embedded` while any target chunk has an empty string, null, or otherwise non-traceable `vector_ref`

Recommended operational rule:

- make failure messages explicit enough to distinguish provider failure, vector backend failure, and SQLite write-back failure

## Re-embed Policy

Phase 2D needs an explicit policy for repeated embedding runs.

Recommended rule:

- allow repeated embedding runs for papers in `chunked`
- treat repeated runs as rebuild or repair operations

Recommended behavior:

- before rewriting vectors, use Chroma collection operations that support explicit delete-and-replace behavior
- remove old Chroma entries referenced by existing `vector_ref`
- clear or replace stale `vector_ref` values in SQLite as part of the rebuild flow
- write fresh vectors
- write fresh `vector_ref`
- only then move or keep the paper in `embedded`

Important constraint:

- repeated embed should not require re-running Phase 2C chunk extraction
- Phase 2D operates on persisted chunks, not raw PDF text

## File and Responsibility Plan

Likely files to touch in a future execution phase:

- Modify: `backend/src/services/memory_store.py`
  - add helpers for reading chunks ready for embedding
  - add helpers for updating `vector_ref`
  - add helpers for clearing or rebuilding `vector_ref` during re-embed
- Modify: `backend/src/services/knowledge_base.py`
  - optionally keep Phase 2C responsibilities only, unless the repo prefers a combined knowledge-ingestion service
- Create or modify: `backend/src/services/vector_store.py`
  - define the thin backend abstraction with Chroma as the concrete first backend
- Create or modify: `backend/src/services/embedding_service.py`
  - define the embedding-provider abstraction
- Modify: `backend/src/main.py`
  - expose the Phase 2D route or evolve `/embed` into a status-aware multi-phase handler only if that remains easy to reason about
- Modify: `backend/src/services/schemas.py`
  - add any response models or backend-config enums if needed
- Modify: `backend/src/tests/test_memory_store.py`
  - cover `vector_ref` write-back and rebuild behavior
- Modify or add: `backend/src/tests/test_knowledge_base.py`
  - only if Phase 2D responsibilities stay in that service
- Add: `backend/src/tests/test_vector_store.py`
  - backend-abstraction contract tests with Chroma-shaped fakes
- Add: `backend/src/tests/test_embedding_service.py`
  - provider-abstraction contract tests with fakes
- Modify: `backend/src/tests/test_api_mvp.py`
  - Phase 2D API behavior tests
- Modify later: `README.md`
  - document the difference between `chunked` and `embedded`

## API Shape Recommendation

This plan does not force a single endpoint shape, but it recommends one of two safe paths:

### Path A: Keep `/embed`, make it phase-aware

Pros:

- minimal API surface change
- keeps the lifecycle discoverable for clients

Cons:

- handler logic becomes more stateful and easier to overcomplicate
- Phase 2C and Phase 2D semantics can blur if the branching is not explicit

Safe rule if this path is chosen:

- `uploaded` triggers Phase 2C
- `chunked` triggers Phase 2D
- any other state returns a clear error

### Path B: Split the endpoint

Pros:

- cleaner semantics
- easier testing
- lower risk of mixing chunking and embedding logic

Cons:

- slightly larger API surface

Safe rule if this path is chosen:

- keep current `/embed` for Phase 2C only, or rename it later for clarity
- add a dedicated Phase 2D endpoint such as `/papers/{paper_id}/embed_vectors`

Default recommendation:

- prefer **Path B** if the team wants clearer lifecycle semantics and easier tests
- prefer **Path A** only if preserving the existing endpoint is a strong UX requirement

## Testing Strategy

Phase 2D should stay highly testable without any real provider or real vector backend in unit tests.

### 1. Store Tests

Need to verify:

- list chunk rows for a `chunked` paper
- update `vector_ref` for one chunk
- bulk write `vector_ref` for all chunks of a paper
- clear stale `vector_ref` during rebuild
- detect whether all chunks for a paper have non-null `vector_ref`

### 2. Service Tests

Need to verify:

- embedding phase only accepts `chunked` papers
- missing chunks fail clearly
- provider failure keeps status at `chunked`
- vector backend failure keeps status at `chunked`
- partial write-back does not promote to `embedded`
- success writes all `vector_ref` values before status change

### 3. API Tests

Need to verify:

- `chunked` paper becomes `embedded` after successful Phase 2D
- success response includes `paper_id`, `status=embedded`, and a useful count field such as `embedded_chunk_count`
- non-`chunked` paper returns `400`
- missing paper returns `404`
- embedding failure keeps paper in `chunked`
- vector backend failure keeps paper in `chunked`
- repeated embedding run replaces stale `vector_ref` safely
- any missing or empty `vector_ref` prevents promotion to `embedded`

### 4. Fake-Backend Contract Tests

Need to verify:

- the vector-store abstraction returns parseable backend ids
- the Chroma adapter can produce app-level `vector_ref` strings through the chosen contract
- delete-and-replace semantics are explicit at the adapter boundary

### 5. Optional Integration Tests Later

Allowed only after the unit/API baseline is stable:

- one opt-in local integration test with a real chosen backend
- no requirement for external network in default CI

## Design Review Points

These decisions should be consciously confirmed before implementation starts:

1. Backend choice
   - Confirm Chroma as the locked default Phase 2D backend for the current MVP line
2. Endpoint strategy
   - Decide whether Phase 2D keeps `/embed` and branches by status, or gets a dedicated endpoint
3. `vector_ref` format
   - Confirm the final string format and whether it includes backend, collection/index, and chunk uid
4. Re-embed semantics
   - Confirm whether repeated Phase 2D runs replace old vectors automatically
5. Success contract
   - Confirm what the success response should include beyond `paper_id` and `status`
6. `page_number` timing
   - Confirm that `page_number` is explicitly deferred beyond Phase 2D
7. Chunk policy configuration
   - Confirm that `PDF_CHUNK_SIZE=3000` and `PDF_CHUNK_OVERLAP=400` are initial defaults only
8. BGE-M3 runtime shape
   - Confirm whether the first version uses a local model route or a service route
9. Provider dependencies
   - Confirm whether `sentence-transformers` / HuggingFace dependencies are acceptable in the first implementation
10. Embedding validation
   - Confirm whether embedding dimensionality should be checked at startup
11. Config exposure
   - Confirm whether `chunk_size` and `overlap` should be surfaced through config in the first implementation

## Recommended Execution Sequence

When the team is ready to implement Phase 2D, the safest order is:

1. freeze Chroma as the backend and freeze `vector_ref` format
2. add store helpers for `vector_ref` read/write/clear/check
3. add fake embedding-provider and fake vector-store tests
4. add Phase 2D service tests
5. add Phase 2D API tests
6. implement the minimal embedding phase behind abstractions
7. update README only after the code and tests are green

## Done Criteria

Phase 2D should be considered complete only when all of the following are true:

- a paper can move from `chunked` to `embedded`
- Phase 2D starts only from `chunked`
- real embedding writes occur through a backend abstraction
- BGE-M3 is the documented default embedding-provider direction
- Chroma is the documented default vector backend
- every embedded chunk row has a traceable non-null `vector_ref`
- no paper becomes `embedded` while any target chunk lacks a non-empty traceable `vector_ref`
- papers stay in `chunked` when embedding or vector write fails
- repeated embedding runs have an explicit repair or rebuild policy
- tests cover store, service, and API failure paths
- docs explain that `embedded` now means real embedding completion, not just chunk persistence

## Ownership Split

Especially worth personal review by the project lead:

- Chroma decision and why it is phase-appropriate
- BGE-M3 decision and whether the first version should be local-model or service-based
- exact meaning of `embedded`
- `vector_ref` format and traceability standard
- whether to keep `/embed` or split the endpoint
- rebuild policy for repeated embedding runs

Reasonably delegable later:

- store helper implementation
- fake backend test scaffolding
- API test wiring
- README sync after behavior is implemented
