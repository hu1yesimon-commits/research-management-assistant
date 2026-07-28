# Agent Team V3 Demo UX Real QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the V3 demo path feel like a research agent while keeping the workflow stable: persistent Chroma/BGE knowledge retrieval, DeepSeek-backed Leader responses, clearer Knowledge UI states, and Idea Assistant as the explicit structured-log surface.

**Architecture:** Keep planning and response generation separate. `leader_provider` continues to return bounded `LeaderPlan`; a new `leader_response_provider` turns typed agent results into user-friendly session replies. Knowledge QA must be verified through persistent vector retrieval, not only SQLite chunks.

**Tech Stack:** FastAPI, Pydantic, SQLite, Chroma, BGE-M3, LangChain `ChatOpenAI` DeepSeek-compatible endpoint, Vue, Vitest, pytest.

---

### Task 1: Make Persistent Knowledge Retrieval the Demo Default

**Files:**
- Modify: `backend/src/config.py`
- Modify: `README.md`
- Test: `backend/src/tests/test_vector_store.py`
- Test: `backend/src/tests/test_embedding_service.py`

- [ ] **Step 1: Write a failing config test for demo retrieval defaults**

Add a test asserting the demo environment instructions use persistent retrieval settings. If there is no existing README config test, add the assertion to the closest config/default test:

```python
def test_demo_retrieval_environment_uses_persistent_vector_stack():
    configured = Config(
        vector_backend="chroma",
        embedding_provider="bge-m3",
        chroma_persist_dir="backend/data/vector_store/chroma",
    )

    assert configured.vector_backend == "chroma"
    assert configured.embedding_provider == "bge-m3"
    assert configured.chroma_persist_dir.endswith("chroma")
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_vector_store.py backend/src/tests/test_embedding_service.py -q
```

Expected: the new assertion fails if the target config/documented demo defaults are not represented.

- [ ] **Step 3: Add explicit demo environment commands**

Do not silently change all offline defaults if that breaks the offline MVP. Add a README demo block:

```bash
export VECTOR_BACKEND=chroma
export EMBEDDING_PROVIDER=bge-m3
export CHROMA_PERSIST_DIR=backend/data/vector_store/chroma
export ANSWER_PROVIDER=deepseek
export DEEPSEEK_API_KEY=...
export DEEPSEEK_BASE_URL=...
```

Keep the code default as `fake` unless the full offline suite is intentionally migrated. The demo command must be explicit so the user can explain deterministic offline mode versus real persistent retrieval.

- [ ] **Step 4: Verify persistent retrieval manually**

Run a real embed/search cycle after starting the backend with the demo env:

```bash
curl -s http://127.0.0.1:8000/knowledge/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"<known phrase from uploaded PDF>","top_k":5}'
```

Expected: `results` contains at least one embedded chunk from a saved paper.

### Task 2: Add `leader_response_provider` Without Changing Planner Semantics

**Files:**
- Modify: `backend/src/config.py`
- Modify: `backend/src/agent_team/planner.py`
- Modify: `backend/src/agent_team/providers.py`
- Modify: `backend/src/main.py`
- Test: `backend/src/tests/test_leader_planner.py`

- [ ] **Step 1: Write failing provider config tests**

Add tests:

```python
def test_config_accepts_independent_leader_response_provider():
    configured = Config(leader_response_provider="deepseek")

    assert configured.leader_response_provider == "deepseek"
    assert configured.leader_provider == "deterministic"


def test_config_rejects_unknown_leader_response_provider():
    with pytest.raises(ValueError, match="Unsupported provider"):
        Config(leader_response_provider="unknown")
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_leader_planner.py -q
```

Expected: tests fail because `leader_response_provider` does not exist yet.

- [ ] **Step 3: Add the config field**

Add fields:

```python
leader_response_provider: str = "deepseek"
leader_response_model: str = "deepseek-chat"
leader_response_temperature: float = 0.2
```

Validate with `validate_provider_name`. Read env vars:

```python
leader_response_provider=os.getenv("LEADER_RESPONSE_PROVIDER", "deepseek")
leader_response_model=os.getenv("LEADER_RESPONSE_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
leader_response_temperature=float(os.getenv("LEADER_RESPONSE_TEMPERATURE", "0.2"))
```

- [ ] **Step 4: Implement an LLM response adapter with deterministic fallback**

Create a responder class that implements the existing `LeaderResponder` protocol:

```python
class LLMLeaderResponder:
    def __init__(self, chat_model, fallback: LeaderResponder | None = None):
        self.chat_model = chat_model
        self.fallback = fallback or DeterministicLeaderResponder()

    def respond(self, planner_input, plan, results):
        prompt = LeaderResponsePromptBuilder().build(planner_input, plan, results)
        try:
            response = self.chat_model.invoke(prompt)
        except Exception:
            return self.fallback.respond(planner_input, plan, results)
        content = getattr(response, "content", response)
        text = content.strip() if isinstance(content, str) else str(content).strip()
        return text or self.fallback.respond(planner_input, plan, results)
```

Prompt constraints:

```text
You are the user-facing research team leader.
Use only typed agent results supplied below.
Do not invent papers, scores, citations, source text, or saved knowledge.
If research completed, summarize count and point the user to Active Candidates.
If knowledge completed with sources, answer in a concise grounded way.
If knowledge has no sources, say local evidence was not found and suggest search or upload/embed.
If a step failed, explain what happened and give the next practical action.
Keep the answer under 120 words.
```

- [ ] **Step 5: Wire `get_leader_responder()`**

In `backend/src/main.py`, return:

```python
def get_leader_responder():
    return build_leader_responder(config)
```

`build_leader_responder()` should return `DeterministicLeaderResponder()` only when `LEADER_RESPONSE_PROVIDER=deterministic`; otherwise it should construct a DeepSeek/OpenAI-compatible chat model and wrap it with fallback.

- [ ] **Step 6: Verify provider tests GREEN**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_leader_planner.py -q
```

Expected: all planner/responder tests pass.

### Task 3: Fix Knowledge Panel State Semantics

**Files:**
- Modify: `frontend/src/components/ResearchWorkbench.vue`
- Modify: `frontend/src/components/KnowledgePanel.vue`
- Test: `frontend/src/components/__tests__/KnowledgePanel.test.js`
- Test: `frontend/src/components/__tests__/ResearchWorkbench.test.js`

- [ ] **Step 1: Write failing UI tests**

Add tests:

```javascript
test("shows not-run state when knowledge is disabled", () => {
  const wrapper = mount(KnowledgePanel, {
    props: { knowledge: { enabled: false, answer: null, sources: [], mode: null, error: null } },
  });

  expect(wrapper.text()).toContain("Not run");
  expect(wrapper.text()).toContain("Ask about saved papers after embedding a PDF.");
});

test("shows no-match state when knowledge ran without sources", () => {
  const wrapper = mount(KnowledgePanel, {
    props: {
      knowledge: {
        enabled: true,
        answer: "No relevant knowledge chunks were found.",
        sources: [],
        mode: "deterministic",
        error: null,
      },
    },
  });

  expect(wrapper.text()).toContain("No relevant knowledge chunks were found.");
  expect(wrapper.text()).toContain("No matching embedded chunks returned.");
});
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
cd frontend && npm test -- KnowledgePanel ResearchWorkbench
```

Expected: tests fail because current copy says `Disabled` and `No knowledge answer yet`.

- [ ] **Step 3: Update default section and copy**

In `ResearchWorkbench.vue`, set:

```javascript
const defaultKnowledgeSection = {
  enabled: false,
  answer: null,
  sources: [],
  error: null,
  mode: null,
};
```

In `KnowledgePanel.vue`, render:

```text
Not run
Ask about saved papers after embedding a PDF.
No matching embedded chunks returned.
```

Do not imply retrieval succeeded unless `sources.length > 0`.

- [ ] **Step 4: Verify UI tests GREEN**

Run:

```bash
cd frontend && npm test -- KnowledgePanel ResearchWorkbench
```

Expected: tests pass.

### Task 4: Keep Idea Assistant as the Explicit Structured Log Surface

**Files:**
- Modify: `frontend/src/components/ResearchWorkbench.vue`
- Modify: `frontend/src/components/IdeaAssistantPanel.vue`
- Test: `frontend/src/components/__tests__/ResearchWorkbench.test.js`
- Test: `frontend/src/components/__tests__/IdeaAssistantPanel.test.js`

- [ ] **Step 1: Write a test that Idea Assistant remains discoverable**

Add:

```javascript
test("keeps Idea Assistant as a separate structured log workflow", async () => {
  const wrapper = mount(ResearchWorkbench);
  await flushPromises();

  await wrapper.find("button.legacy-tools__toggle").trigger("click");

  expect(wrapper.text()).toContain("Idea Assistant");
  expect(wrapper.text()).toContain("Structured experiment logs");
});
```

- [ ] **Step 2: Keep it as a manual panel**

Do not add free-text session parsing into experiment logs in this phase. The interview explanation should be:

```text
Session Chat coordinates research and knowledge QA. Idea Assistant is intentionally structured because experiment logs are high-signal data for later memory extraction.
```

- [ ] **Step 3: Verify focused frontend tests**

Run:

```bash
cd frontend && npm test -- ResearchWorkbench IdeaAssistantPanel
```

Expected: tests pass.

### Task 5: Verification and Demo Script

**Files:**
- Modify: `README.md`
- Optional create: `docs/demo/agent-team-v3-demo-script.md`

- [ ] **Step 1: Run backend tests**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend tests and build**

Run:

```bash
cd frontend && npm test && npm run build
```

Expected: all tests pass and Vite build completes.

- [ ] **Step 3: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 4: Manual demo path**

Use this demonstration sequence:

```text
1. Start backend with VECTOR_BACKEND=chroma, EMBEDDING_PROVIDER=bge-m3, ANSWER_PROVIDER=deepseek, LEADER_RESPONSE_PROVIDER=deepseek.
2. Reset demo session if needed, preserving saved embedded papers.
3. Ask Session Chat: "Find recent papers about time series classification algorithms."
4. Show Active Candidates and accept one candidate if needed.
5. Upload/embed one PDF, then confirm /knowledge/search returns chunks.
6. Ask Session Chat: "What does the saved paper say about the method?"
7. Show Knowledge answer, sources, and Agent Trace.
8. Open Idea Assistant and submit a structured experiment log.
9. Explain Memory Summary as review-gated memory concept only; do not demo memory review UI.
```

- [ ] **Step 5: Commit**

Commit message:

```bash
git add backend/src frontend/src README.md docs/demo/agent-team-v3-demo-script.md
git commit -m "feat: improve agent team v3 demo qa experience"
```

---

## Scope Notes

- Do not implement Memory Review UI in this phase.
- Do not auto-parse free-form chat messages into experiment logs.
- Do not let response LLM create planner steps or mutate state.
- Do not remove deterministic fallback for responder failures.
