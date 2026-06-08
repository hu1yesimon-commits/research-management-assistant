# Phase 2C PDF Text Extraction And Knowledge Chunks Checklist

> **For future implementation only:** This checklist is a planning artifact for Phase 2C. It does not mean real embedding, Chroma integration, FAISS integration, or production-grade vector retrieval is already complete.

**Goal:** Implement Phase 2C as a strict `uploaded -> chunked` pipeline that performs PDF text extraction and `knowledge_chunks` persistence without doing real embedding.

**Architecture:** Phase 2C is the chunking phase only. It starts from `uploaded`, reads `pdf_path`, extracts text, splits text into chunks, persists chunk rows, and only then updates the paper to `chunked`. `embedded` remains reserved for a later phase where real embeddings exist and `vector_ref` is written or traceable.

**Tech Stack:** Existing FastAPI service, existing SQLite `MemoryStore`, local filesystem PDFs, local text extraction helper, chunk persistence in SQLite, no Chroma, no FAISS, no real embedding API.

---

## Phase 2C Scope

Phase 2C includes:

- PDF text extraction from local `pdf_path`
- local text cleanup sufficient for chunking
- deterministic chunk splitting
- `knowledge_chunks` table creation and persistence
- repeated chunk rebuild and overwrite behavior
- `uploaded -> chunked` status transition
- `/embed` response including `paper_id`, `status=chunked`, `pdf_path`, `chunk_count`

Phase 2C explicitly does **not** include:

- real embedding generation
- Chroma integration
- FAISS integration
- remote embedding API calls
- `embedded` status promotion

## State Flow

Phase 2C required lifecycle:

`uploaded -> chunked`

Status meanings in this checklist:

- `uploaded` = local PDF file exists and `pdf_path` is recorded
- `chunked` = PDF text extraction succeeded and chunk rows were written into `knowledge_chunks`
- `embedded` = not part of Phase 2C; reserved for a later phase where real embeddings are complete and `vector_ref` is written or traceable

Strict rule:

- failure in Phase 2C must leave the paper in `uploaded`
- Phase 2C must never mark a paper as `embedded`

## File List

Expected files to modify or add during implementation:

- Modify: `backend/src/services/memory_store.py`
  - add `knowledge_chunks` table initialization
  - add chunk insert/list/delete helpers
- Modify: `backend/src/services/knowledge_base.py`
  - add `extract_text(pdf_path)` helper
  - add `chunk_text(text)` helper
- Modify: `backend/src/main.py`
  - change `/papers/{paper_id}/embed` so Phase 2C performs text extraction plus chunk persistence only
  - return `paper_id`, `status`, `pdf_path`, `chunk_count`
- Modify: `backend/src/services/schemas.py`
  - add `chunked` to `PaperStatus`
- Modify: `backend/src/tests/test_memory_store.py`
  - add `knowledge_chunks` persistence tests
- Add or modify: `backend/src/tests/test_knowledge_base.py`
  - add text extraction and chunking helper tests
- Modify: `backend/src/tests/test_api_mvp.py`
  - add Phase 2C `/embed` API behavior tests
- Modify later, after implementation only: `README.md`
  - explain `chunked`
  - keep `embedded` reserved for real embedding completion

## Checklist

### 1. MemoryStore Checklist

- [ ] Add `knowledge_chunks` table to `initialize()`
- [ ] Include at least these fields:
  - `id`
  - `paper_id`
  - `chunk_index`
  - `text`
  - `chunk_hash`
  - `vector_ref`
  - `created_at`
- [ ] Keep `vector_ref` nullable in Phase 2C
- [ ] Add `insert_knowledge_chunks(...)`
- [ ] Add `list_knowledge_chunks(paper_id)`
- [ ] Add `delete_knowledge_chunks_by_paper(paper_id)`
- [ ] Ensure repeated chunk rebuild deletes old rows before inserting new rows

### 2. KnowledgeBase Checklist

- [ ] Add `extract_text(pdf_path)` helper
- [ ] Keep extraction local and deterministic
- [ ] Make extraction failure explicit
- [ ] Treat empty or near-empty extracted text as failure
- [ ] Add `chunk_text(text)` helper
- [ ] Use deterministic fixed-size chunking with overlap
- [ ] Ignore blank chunks
- [ ] Preserve stable `chunk_index`

### 3. `/embed` Phase 2C Checklist

- [ ] Keep existing precondition that paper must exist
- [ ] Keep existing precondition that paper must currently be `uploaded`
- [ ] Validate `pdf_path` exists before extraction
- [ ] Run extraction before any status update
- [ ] Delete old chunks for the paper before writing rebuilt chunks
- [ ] Persist new chunks before any status update
- [ ] Update paper status to `chunked` only after chunk persistence succeeds
- [ ] Return:
  - `paper_id`
  - `status = "chunked"`
  - `pdf_path`
  - `chunk_count`
- [ ] On failure, keep paper in `uploaded`
- [ ] Do not label Phase 2C success as `embedded`

### 4. Repeat Build Checklist

- [ ] Keep `/embed` entry precondition strict: each Phase 2C run still starts from `uploaded`
- [ ] If a paper re-enters Phase 2C from `uploaded`, allow old chunks for the same `paper_id` to be deleted and rebuilt
- [ ] Replace old chunk rows for the same `paper_id`
- [ ] Keep rebuild behavior deterministic for debugging
- [ ] Avoid partial old/new mixed chunk state

## Test List

### Store Tests

- [ ] creates `knowledge_chunks` table during initialization
- [ ] inserts chunk rows for one paper
- [ ] lists chunk rows by `paper_id`
- [ ] deletes chunk rows by `paper_id`
- [ ] rebuild replaces old chunks for the same paper
- [ ] keeps `vector_ref = NULL` in Phase 2C

### Service Tests

- [ ] `extract_text` returns text for a supported PDF fixture
- [ ] `extract_text` fails clearly for invalid or unreadable PDF input
- [ ] empty extracted text is treated as failure
- [ ] `chunk_text` produces deterministic chunk ordering
- [ ] `chunk_text` preserves overlap behavior
- [ ] blank chunks are not emitted

### API Tests

- [ ] uploaded paper becomes `chunked` after successful Phase 2C `/embed`
- [ ] `/embed` response returns `paper_id`, `status=chunked`, `pdf_path`, `chunk_count`
- [ ] non-uploaded paper returns `400`
- [ ] missing paper returns `404`
- [ ] missing or invalid `pdf_path` does not produce `embedded`
- [ ] extraction failure keeps paper in `uploaded`
- [ ] rebuild path overwrites old chunks for the same paper

## PDF Parser Dependency Review

Phase 2C requires choosing one parser for first-pass text extraction.

Recommended first parser to evaluate:

- `pypdf`

Why `pypdf` is a reasonable first candidate:

- simple API surface
- common pure-Python choice
- easier to adopt for a first local MVP pass than a heavier document-processing stack

Risks of choosing `pypdf` for v1:

- extraction quality varies across PDF layouts
- scanned PDFs may effectively produce no usable text
- equations, tables, and multi-column layouts may extract poorly
- extraction success does not imply semantically clean text

Phase 2C parser decision rule:

- choose one parser first
- optimize for predictable local behavior and testability
- do not block chunk persistence work on perfect extraction quality

## User Review Design Points

These design points should be explicitly reviewed before implementation starts:

1. `chunked` status adoption
   - Confirm that Phase 2C should formally add `chunked` to `PaperStatus`
2. `/embed` response shape
   - Confirm that success should always return `paper_id`, `status=chunked`, `pdf_path`, `chunk_count`
3. Extraction failure threshold
   - Confirm whether near-empty text should always be treated as failure
4. Chunking policy
   - Confirm initial chunk size and overlap values
5. Rebuild policy
   - Confirm Phase 2C rebuild should overwrite old chunks when a paper re-enters from `uploaded`, rather than leaving mixed state
6. Parser selection
   - Confirm whether to start with `pypdf` in v1 or evaluate alternatives first

## Non-Goals Reminder

Do not implement any of the following in Phase 2C:

- real embedding generation
- Chroma integration
- FAISS integration
- vector retrieval
- semantic claim that `embedded` is complete

## Done Criteria

Phase 2C should only be considered complete when all of the following are true:

- `PaperStatus` includes `chunked`
- `/embed` begins from `uploaded`
- PDF text is extracted from local `pdf_path`
- `knowledge_chunks` rows are written successfully
- successful Phase 2C requests return `paper_id`, `status=chunked`, `pdf_path`, `chunk_count`
- failed Phase 2C requests leave the paper in `uploaded`
- no Phase 2C path marks a paper as `embedded`
- README is later updated so `chunked` means chunk persistence completed, while `embedded` still means real embedding completion only
