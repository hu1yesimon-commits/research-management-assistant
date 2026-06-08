# Uploaded To Embedded Pipeline Plan

> **For future implementation only:** This document is a planning reference for the next phase. It does not mean real PDF parsing, real embedding, or real vector-store integration is already complete.

**Goal:** Split the future ingestion pipeline into two clearer stages so status meaning stays strict: `uploaded -> chunked -> embedded`.

**Architecture:** Keep the existing FastAPI + SQLite MVP shape, but separate "PDF text extracted and chunk rows persisted" from "real embeddings written and vector references are traceable". In the tightened model, `chunked` means text extraction plus `knowledge_chunks` persistence succeeded, while `embedded` means chunk embeddings were actually created and `vector_ref` values were written or otherwise traceable. This avoids using `embedded` as a premature proxy for partially completed work.

**Tech Stack:** Existing FastAPI service, existing SQLite `MemoryStore`, local filesystem PDFs, future-compatible vector-store abstraction, Chroma as the selected Phase 2D backend.

---

## Current State

What is already true today:

- `POST /papers/{paper_id}/embed` exists in [backend/src/main.py](/Users/nuonuohu/Developer/graphReconstruction/backend/src/main.py).
- It only allows `uploaded` papers to enter `embedded`.
- It currently does **not** parse PDFs.
- It currently does **not** create chunks.
- It currently does **not** call an embedding model.
- It currently does **not** write to Chroma, FAISS, or any other vector store.
- `embedded` currently means only "status flag updated", not "real vectorization complete".

This plan describes the **next implementation phase**, not the current behavior.

## Proposed Pipeline

Recommended future state flow:

`uploaded -> chunked -> embedded`

Recommended meaning of each future state:

- `uploaded` = local PDF file exists and `pdf_path` is recorded, but no verified chunk records or embeddings are implied.
- `chunked` = PDF text extraction succeeded and chunk rows were persisted into `knowledge_chunks`.
- `embedded` = chunks have completed real embedding, and `vector_ref` has been written or is otherwise traceable for every embedded chunk.

Recommended runtime sequence across phases:

1. Read paper metadata from SQLite and verify:
   - paper exists
   - status is `uploaded`
   - `pdf_path` exists on disk
2. Extract raw text from the PDF file.
3. Normalize and clean the extracted text just enough for chunking.
4. Split the text into chunks using a deterministic local chunking strategy.
5. Replace any existing chunk records for that `paper_id`.
6. Persist new rows into `knowledge_chunks`.
7. Update paper status to `chunked` only after chunk persistence succeeds.
8. In a later phase, create real embeddings for persisted chunks.
9. Write `vector_ref` values or another traceable vector identifier per embedded chunk.
10. Update paper status to `embedded` only after embedding and vector reference persistence succeed.

Recommended state rule:

- `chunked` should mean "text extraction and chunk persistence completed successfully".
- `embedded` should mean "real embedding completed and vector references are written or traceable".
- Chunk persistence alone should **not** be labeled as `embedded`.

## Scope Boundaries

This plan includes:

- PDF text extraction
- Chunk splitting
- `knowledge_chunks` table design
- Vector-store selection guidance
- Test strategy
- Repeatable re-embed behavior

This plan does not claim these are already implemented:

- real PDF parsing in production code
- real embedding API calls
- Chroma integration
- FAISS integration
- retrieval or RAG query flow over embedded chunks

## Data Model Plan

Add a new SQLite table: `knowledge_chunks`.

Recommended first-version fields:

- `id`: auto-increment primary key
- `paper_id`: foreign-key-like reference to `papers.paper_id`
- `chunk_index`: stable order within one paper
- `text`: stored chunk text
- `chunk_hash`: deterministic hash of chunk text for debugging and rebuild comparisons
- `vector_ref`: nullable text field in Phase 2C, required-or-traceable field by the time a row is considered truly embedded
- `created_at`: timestamp

Important first-version decision:

- `vector_ref` should be allowed to stay empty during Phase 2C.
- This keeps the schema compatible with a chunk-only pipeline first, while reserving a clean path for later Chroma or FAISS integration in Phase 2D.

## Phase Split

### Phase 2C

Phase 2C should only do:

- PDF text extraction
- text normalization sufficient for chunking
- chunk splitting
- `knowledge_chunks` persistence
- rebuild-and-overwrite behavior for repeated chunk generation

Phase 2C should not do:

- real embedding
- vector-store writes
- promotion to a semantically meaningful `embedded` state

Preferred state outcome for Phase 2C:

- `uploaded -> chunked`

If the current codebase is not ready to add a new `chunked` status immediately, the temporary fallback should be documented as:

- keep the paper in `uploaded`
- persist `knowledge_chunks`
- expose chunk_count or inspectable chunk rows for debugging
- do **not** relabel that condition as `embedded`

### Phase 2D

Phase 2D should do:

- read persisted `knowledge_chunks`
- generate real embeddings for chunks
- write to the chosen vector backend
- persist `vector_ref` or another traceable vector identifier
- transition `chunked -> embedded`

Phase 2D is the first phase where `embedded` should become true in the strict sense.

## Repeat Embed Strategy

Recommended behavior for repeated embed requests:

- Allow rebuild and overwrite old chunk state for the same `paper_id`.
- Before persisting newly generated chunks, delete old `knowledge_chunks` rows for that paper.
- If a vector backend exists later, old vector references should be deleted or replaced in the same rebuild flow.

Reason:

- This is simpler than rejecting repeat embed calls.
- It gives a practical recovery path after parser changes, chunking changes, or previous failed runs.
- It matches the current MVP preference for manual recovery over workflow dead-ends.

## PDF Text Extraction Plan

First implementation goal:

- Make text extraction local, deterministic, and inspectable.

Recommended behavior:

- Read bytes from `pdf_path`.
- Attempt text extraction through one PDF parser only.
- If extraction fails completely, return a clear failure and keep status as `uploaded`.
- If extraction returns empty or near-empty text, treat that as a failure for chunking readiness.

Non-goals for v1:

- perfect handling of scanned PDFs
- OCR
- equation-aware parsing
- table-aware parsing
- layout reconstruction

## Chunking Plan

Recommended first-version chunking strategy:

- fixed-size text windows
- fixed overlap
- deterministic ordering

Reason:

- Easier to test than semantic chunking
- Easier to diff across rebuilds
- Good enough to validate Phase 2C chunk persistence before optimizing retrieval quality

Suggested chunking requirements:

- ignore blank chunks
- preserve `chunk_index`
- ensure overlap is consistent
- keep chunk size policy documented in code comments and README updates when the feature lands

## Vector Store Selection Guidance

Project conclusion for the current MVP line:

- choose **Chroma** as the Phase 2D vector backend

Why this is the chosen direction:

- the current project priority is to stabilize the business lifecycle around `chunked -> embedded`
- Chroma reduces first-pass integration cost for local development and chunk metadata association
- the main engineering risk right now is not vector-index sophistication, but status semantics, failure recovery, and `vector_ref` traceability
- FAISS remains a valid future reevaluation option, but it is not the selected default for this repo now

Recommended architectural rule:

- Keep vector-store usage behind a thin service boundary.
- Do not couple `embed` endpoint behavior directly to a specific Chroma or FAISS API surface.
- Do not treat chunk persistence as a substitute for embedding completion.

Practical phased recommendation:

- In Phase 2C, land `knowledge_chunks` plus text/chunk persistence first.
- In Phase 2D, wire real Chroma writes and only then adopt a strict `embedded` state.

## Failure Handling Plan

Future implementation should distinguish at least these cases:

- `404`: paper does not exist
- `400`: paper is not `uploaded`
- `409` or `400`: paper has no valid `pdf_path`
- `422` or `500`: PDF extraction failed or produced unusable text
- `422` or `500`: embedding/vector-write phase failed after chunking

State rule:

- Never mark a paper as `embedded` unless real embedding completed and vector references are written or traceable.
- If extraction or chunk persistence fails, paper should remain `uploaded` or move only to `chunked` when that status is implemented correctly.
- If embedding fails after chunk persistence, paper should remain `chunked`, not `embedded`.

## Testing Strategy

Recommended test layers:

### 1. Service-Level Unit Tests

Target:

- PDF path validation
- extraction failure handling
- empty-text handling
- chunk count and ordering
- repeat embed rebuild behavior
- embedding precondition behavior once Phase 2D starts

Focus:

- deterministic local behavior
- no network dependency
- no real vector backend dependency in the first pass

### 2. Store-Level Tests

Target:

- `knowledge_chunks` table creation
- insert rows for one paper
- delete-and-rebuild on repeated embed
- preserve `vector_ref = NULL` in Phase 2C
- persist non-empty or traceable `vector_ref` in Phase 2D

### 3. API Tests

Target:

- uploaded paper can become `chunked` after successful Phase 2C pipeline run
- chunked paper can become `embedded` after successful Phase 2D embedding run
- non-uploaded paper still returns `400`
- missing paper still returns `404`
- extraction failure leaves paper in `uploaded`
- embedding failure leaves paper in `chunked`

### 4. Manual Smoke Checks

Target:

- upload a local PDF
- trigger the chunking phase
- inspect chunk persistence
- confirm `pdf_path` remains stable
- later trigger embedding and inspect vector traceability

## Recommended Delivery Sequence

1. Add `knowledge_chunks` schema support.
2. Add store helpers for chunk insert, lookup, and delete-by-paper.
3. Add local extraction and chunking helpers to `knowledge_base`.
4. Implement Phase 2C: `uploaded -> chunked` with no real embedding.
5. Add service/store/API tests for chunking success and failure paths.
6. After chunk persistence is stable, implement Chroma-backed Phase 2D integration behind a thin abstraction.
7. Implement Phase 2D: `chunked -> embedded` with real embeddings and `vector_ref` traceability.
8. Add service/store/API tests for embedding success and failure paths.

## Risks

### State Drift

Biggest risk:

- paper gets marked `embedded` before embeddings are actually persisted or traceable

Mitigation:

- separate `chunked` from `embedded`
- update status only after the correct phase completes

### Parser Fragility

PDF extraction quality is inherently unstable across different PDFs.

Mitigation:

- treat parser output as best-effort
- fail closed on empty extraction
- keep rebuild capability

### Backend Coupling Risk

Even with Chroma selected, direct application-level coupling can still slow future changes.

Mitigation:

- keep `vector_ref` nullable in Phase 2C only
- keep vector backend behind a thin abstraction
- land chunk persistence before vector integration if needed

### Rebuild Complexity

Repeated embed without a rebuild rule leads to inconsistent chunk state.

Mitigation:

- explicitly allow rebuild
- overwrite old chunks per `paper_id`

## Definition Of Done For The Future Real Version

This plan should only be considered implemented when all of the following become true in code:

- the chunking phase still begins from `uploaded`
- PDF text is actually extracted from `pdf_path`
- chunk rows are actually written into `knowledge_chunks`
- repeated rebuilds replace old chunks
- Phase 2C does not claim chunk persistence equals embedding completion
- `embedded` only becomes true after real chunk embeddings exist and `vector_ref` is written or traceable
- README is updated to distinguish `chunked` from `embedded`, while avoiding any false claim that chunk persistence alone equals vectorization complete
