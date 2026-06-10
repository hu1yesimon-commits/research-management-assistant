# Research Management Assistant Interview Q&A

Use this document to prepare for technical interviews. Keep answers concise, honest, and tied to implemented behavior.

## 1. What problem does this project solve?

It helps a researcher manage the loop from literature discovery to knowledge reuse and experiment ideation. The system supports finding candidate papers, saving selected papers, uploading PDFs, chunking and embedding them, retrieving grounded evidence, answering with sources, logging experiments, reviewing memory candidates, and generating evidence-backed idea options.

The important part is the workflow: papers are not just searched once; they can enter a controlled lifecycle and later support retrieval, answers, and experiment ideas.

## 2. Why split discovery and knowledge retrieval?

Discovery and knowledge retrieval answer different questions.

Discovery asks:

```text
What new papers might I read?
```

Knowledge retrieval asks:

```text
What evidence already exists in my local knowledge base?
```

I keep them separate because discovery candidates have not been verified, uploaded, or embedded yet. They should not be used as grounded answer sources. Grounded answers only cite embedded local chunks.

## 3. Why not automatically save all discovery results?

Automatically saving every search result pollutes the research library. A discovery result means "the system found this paper"; it does not mean "the user wants to keep this paper".

The current design is:

```text
discovery candidate -> user Accept -> saved candidate in SQLite
```

This keeps SQLite as a user-curated research library instead of a raw search-history cache.

## 4. Explain the paper lifecycle.

The discovery-driven path is:

```text
discovery candidate -> accepted -> uploaded -> chunked -> embedded
```

State meanings:

- `discovery candidate`: temporary query result, not saved by default.
- `accepted`: user saved this paper to SQLite.
- `uploaded`: PDF file is saved and `pdf_path` is recorded.
- `chunked`: PDF text extraction and chunk persistence succeeded.
- `embedded`: every target chunk has a non-empty, traceable `vector_ref`.

Future manual path:

```text
manual PDF upload -> uploaded -> chunked -> embedded
```

## 5. Why add `chunked` instead of directly going to `embedded`?

`chunked` prevents state drift. PDF text extraction and chunk persistence are not the same as vector embedding.

Benefits:

- inspect extracted text quality
- compare chunking strategies
- rebuild chunks after parser changes
- avoid claiming vectorization finished before vector references exist
- support debugging when embedding or Chroma write fails

## 6. Why store chunks in SQLite instead of only in a vector database?

SQLite chunk persistence gives a debuggable intermediate layer.

It lets me inspect what text was extracted, what chunk hash was produced, what chunk index belongs to which paper, and what `vector_ref` maps the chunk to the vector store. This makes the ingestion pipeline easier to test, rebuild, and explain.

## 7. What does `vector_ref` mean?

`vector_ref` is a traceable reference from SQLite chunk rows to vector-store records.

Current format:

```text
chroma:<collection_name>:<chunk_uid>
```

It is not the vector itself. It is a stable link that proves the chunk has been written to the vector backend.

## 8. Why use provider abstractions?

The project separates provider interfaces from workflow logic.

Examples:

- `EmbeddingService`: fake or BGE-M3
- `VectorStoreService`: fake or Chroma
- answer generator: deterministic or DeepSeek/OpenAI
- paper judge: mock or DeepSeek

This keeps default tests offline and deterministic while allowing real local/manual smoke paths.

## 9. Why default to deterministic/offline providers?

For repeatable tests and stable demos.

External APIs, model downloads, vector stores, and LLM calls can fail due to network, credentials, rate limits, or local environment. The default path should verify contracts and workflow behavior without those dependencies. Real providers are opt-in and validated through manual smoke checks.

## 10. How does paper scoring work?

The paper judge provider produces intermediate judge fields:

- `decision`
- `reason`
- `tags`
- `llm_relevance_score`
- `quality_score`

`ScoreUtils` computes deterministic sub-scores and final score. The final score is not directly produced by the LLM.

Current weights:

```text
llm_relevance_score: 0.40
embedding_relevance_score: 0.15
quality_score: 0.25
novelty_score: 0.20
```

This gives LLM relevance the highest weight while preserving deterministic, explainable scoring.

## 11. Why not let the LLM output `final_score` directly?

Because final ranking should be controllable and testable.

If the LLM outputs the final score directly, the scoring policy becomes hidden inside model behavior. By asking the LLM only for semantic sub-scores and using `ScoreUtils` for final aggregation, the project keeps the ranking policy explicit and easier to test.

## 12. How do you handle missing abstracts?

Missing abstracts are treated conservatively. The system can return `uncertain` and avoid overconfident scoring. This prevents low-information papers from being ranked as strong candidates just because metadata exists.

If the user later uploads a PDF and the abstract/text can be extracted, the paper can be reprocessed with richer context.

## 13. What happens if judging one paper fails?

The graph uses per-item fault isolation. A single judge failure should not crash the whole discovery batch.

The failed paper gets a fallback result:

- `decision="uncertain"`
- tag includes `judge_failed`
- final score is still computed from fallback sub-scores

Other papers continue normally.

## 14. How does the system reduce hallucination in answers?

Grounded answers use retrieved sources from embedded chunks. The answer generator receives sources as input, and response sources come from retrieval results, not from the LLM.

If no sources are found, the system returns a fallback instead of forcing an answer.

## 15. How does Idea Assistant work?

The Idea Assistant is driven by structured experiment logs submitted by the user.

Example fields:

- task
- model
- metric/problem
- tried methods
- observation
- goal

The system builds a retrieval query, looks for relevant knowledge chunks, and returns idea options with:

- rationale
- supporting evidence
- expected benefit
- risk
- validation metric
- next experiment

The MVP default is deterministic/offline. It is not claimed as a fully autonomous research agent.

## 16. Why make Idea Assistant log-driven instead of chat-driven?

Structured logs are easier to test and less likely to pollute memory. They force the user to state the actual experiment context: task, model, metric, observation, and tried methods.

Free-form chat memory is useful later, but it needs extraction, confirmation, and forgetting rules. For MVP, user-submitted structured logs are safer.

## 17. What is the Memory System MVP?

The Memory System MVP has three layers:

- `experiment_log_entries`: episodic evidence from structured experiment logs.
- `memory_candidates`: proposed long-term memory items requiring review.
- `semantic_memory`: user-confirmed long-term facts.

Confirmed memory can be used as context for future workflows. Candidate memory is not automatically trusted.

## 18. How is this different from saving chat history?

Chat history is a raw transcript. A memory system is selective, structured, reviewable, and retrievable.

The project does not treat every conversation as memory. It promotes only meaningful, user-reviewed information into long-term memory.

## 19. What about stale/conflicting memory?

The current MVP treats stale/conflict handling as review-gated future work. It does not automatically rewrite or delete confirmed semantic memory just because time has passed or a new log appears.

This is intentional. Incorrect automatic memory updates can corrupt long-term context.

## 20. Why not use Neo4j and Qdrant now?

They are valuable for a more advanced memory system, but they would be too heavy for this MVP.

Current storage already covers the main demo path:

- SQLite for paper state, chunks, logs, memory review
- Chroma as optional vector backend for knowledge chunks

A future migration can add graph/vector memory retrieval after the workflow semantics are stable.

## 21. What is the role of LangGraph?

LangGraph is used to keep paper discovery as an explicit workflow rather than an uncontrolled agent loop.

The graph separates stages such as query rewrite, search, dedup, judge, rank, and persistence boundaries. This makes the system easier to test and explain.

## 22. Why use FastAPI?

FastAPI gives clear endpoint contracts, dependency injection, request validation, and good testing support through `TestClient`.

This fits the project because the backend is organized as services and workflows, not just scripts.

## 23. What does the frontend demonstrate?

The Vue Research Workbench demonstrates the main workflow:

- backend health status
- unified research query
- discovery and knowledge sections
- saved candidate lifecycle
- PDF upload/embed controls
- Idea Assistant panel

It is a focused MVP workbench, not a production UI.

## 24. What tests do you have?

The project has pytest coverage for:

- API endpoints
- graph workflow behavior
- SQLite persistence
- scoring utilities
- paper judge behavior
- embedding/vector abstractions
- retrieval and grounded answer
- Idea Assistant
- memory review workflow

The frontend has Vitest component tests and a production build check.

## 25. What real smoke tests have been verified?

The project has a default offline smoke script covering the stable local MVP path. Optional real provider smoke has also been used for paths such as BGE-M3 + Chroma and DeepSeek judge/answer, but those are not part of the default test path.

External discovery can still be affected by arXiv/OpenAlex network/API behavior.

## 26. What are the known limitations?

- External discovery can timeout or be rate-limited.
- Default providers are deterministic/offline.
- Idea Assistant is MVP-level and deterministic by default.
- Memory stale/conflict handling is future work.
- PDF parsing has no OCR or complex layout recovery.
- Frontend is an MVP workbench, not production UX.
- No SSE/multiround chat/full autonomous agent planner yet.

## 27. What would you improve next?

I would prioritize:

1. stronger evaluation for paper judge quality
2. real provider smoke documentation and repeatability
3. better PDF parsing quality and metadata validation
4. memory stale/conflict review workflow
5. richer frontend review UI for memory and idea workflows

I would not add all of these before interview. The current project is intentionally frozen for stabilization and demo readiness.

## 28. Why is this project suitable for an Agent developer role?

It demonstrates agentic workflow design without turning everything into an uncontrolled chatbot. The project uses:

- explicit workflow orchestration
- tool/provider abstraction
- structured outputs
- memory review boundaries
- retrieval grounding
- fallback behavior
- deterministic tests
- optional real LLM/vector providers

This is close to how practical agent systems are built in production: bounded autonomy, observable state, and clear failure handling.

## 29. How does your previous technical support/testing experience connect?

The project reflects habits from technical support and testing work:

- structure ambiguous user problems into reproducible records
- preserve evidence and source context
- separate observed facts from hypotheses
- design fallback behavior
- write regression tests for workflow failures
- make troubleshooting steps visible

This is why the system emphasizes experiment logs, memory review, sources, and deterministic smoke tests.

## 30. Short answer when asked "Is this production-ready?"

No. It is a resume-grade MVP with a real architecture and tested workflows. It demonstrates the core design patterns: discovery, ingestion, retrieval, grounded answer, idea recommendation, memory review, and provider abstraction. Production work would require stronger evaluation, security, deployment, observability, more robust PDF parsing, and richer provider monitoring.
