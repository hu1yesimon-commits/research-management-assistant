# Research Workbench Assistant-First Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reshape the current Research Workbench into an assistant-first homepage with a separate assistant summary layer, a collapsed saved-candidates lifecycle drawer, and a lightweight memory summary card while keeping Idea Assistant independent.

**Architecture:** First align the backend memory summary contract with the frontend spec so the UI can read stable counts from a single endpoint. Then add focused Vue components for assistant summary and memory summary, re-orchestrate `ResearchWorkbench.vue` around explicit result-source and collapse state, and finish with layout/test hardening that preserves the existing assistant/query fallback behavior.

**Tech Stack:** FastAPI, SQLite-backed `MemoryStore`, Vue 3, Vite, Vitest, Vue Test Utils

---

## File Structure

**Create**

- `frontend/src/components/AssistantSummaryPanel.vue`
- `frontend/src/components/MemorySummaryCard.vue`
- `frontend/src/components/__tests__/AssistantSummaryPanel.test.js`
- `frontend/src/components/__tests__/MemorySummaryCard.test.js`
- `docs/superpowers/plans/2026-06-27-research-workbench-assistant-first-implementation.md`

**Modify**

- `backend/src/main.py`
- `backend/src/tests/test_api_mvp.py`
- `frontend/src/api.js`
- `frontend/src/components/ResearchWorkbench.vue`
- `frontend/src/components/AssistantWorkflowPanel.vue`
- `frontend/src/components/CandidateLifecyclePanel.vue`
- `frontend/src/components/QueryForm.vue`
- `frontend/src/components/__tests__/ResearchWorkbench.test.js`
- `frontend/src/components/__tests__/AssistantWorkflowPanel.test.js`
- `frontend/src/styles.css`

**Primary Verification Targets**

- `backend/src/tests/test_api_mvp.py`
- `frontend/src/components/__tests__/AssistantSummaryPanel.test.js`
- `frontend/src/components/__tests__/MemorySummaryCard.test.js`
- `frontend/src/components/__tests__/AssistantWorkflowPanel.test.js`
- `frontend/src/components/__tests__/ResearchWorkbench.test.js`

### Task 1: Align The Memory Summary API Contract

**Files:**
- Modify: `backend/src/main.py`
- Modify: `backend/src/tests/test_api_mvp.py`

- [ ] **Step 1: Write the failing backend API test**

Add this test near the other API endpoint tests in `backend/src/tests/test_api_mvp.py`:

```python
def test_memory_summary_returns_review_and_confirmed_counts(tmp_path):
    test_db = tmp_path / "api-memory-summary.sqlite3"
    store = get_memory_store(str(test_db))

    candidate_id = store.upsert_memory_candidate(
        {
            "candidate_type": "semantic_proposal",
            "category": "experiment_target",
            "subject": "graph reconstruction",
            "predicate": "uses_object",
            "object": "contrastive loss",
            "summary": "graph reconstruction repeatedly uses contrastive loss",
            "source_log_ids": [1, 2, 3],
            "evidence_count": 3,
            "score": 0.82,
            "status": "pending",
        }
    )
    store.upsert_semantic_memory_from_candidate(
        {
            "candidate_type": "semantic_proposal",
            "category": "user_preference",
            "subject": "user",
            "predicate": "prefers",
            "object": "local-first workflows",
            "summary": "User repeatedly prefers local-first workflows",
            "source_log_ids": [4, 5, 6],
            "evidence_count": 3,
            "score": 0.9,
            "status": "accepted",
        }
    )
    store.add_experiment_log("latest log", ["graph"])

    app.dependency_overrides[get_memory_store] = override_store_with_path(test_db)
    client = TestClient(app)

    response = client.get("/memory/summary")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "candidate_count": 0,
        "saved_paper_count": 0,
        "pending_candidate_count": 1,
        "confirmed_memory_count": 1,
        "known_doi_count": 0,
        "recent_logs": [{"content": "latest log", "tags": ["graph"]}],
    }
```

- [ ] **Step 2: Run the focused backend test to verify it fails**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_api_mvp.py::test_memory_summary_returns_review_and_confirmed_counts -q
```

Expected: FAIL because `/memory/summary` only returns `candidate_count`, `known_dois`, and `recent_logs`.

- [ ] **Step 3: Update the endpoint implementation**

Replace the existing `/memory/summary` handler in `backend/src/main.py` with:

```python
@app.get("/memory/summary")
def memory_summary(store: MemoryStore = Depends(get_memory_store)):
    saved_candidates = store.list_candidate_papers()
    pending_candidates = store.list_memory_candidates(status="pending")
    confirmed_memories = store.list_semantic_memory(status="confirmed")
    known_dois = store.list_known_dois()
    recent_logs = store.list_experiment_logs(limit=5)

    return {
        "candidate_count": len(saved_candidates),
        "saved_paper_count": len(saved_candidates),
        "pending_candidate_count": len(pending_candidates),
        "confirmed_memory_count": len(confirmed_memories),
        "known_doi_count": len(known_dois),
        "recent_logs": recent_logs,
    }
```

- [ ] **Step 4: Update the test expectation to match the actual log payload shape**

If the log record includes generated `id` data, use this exact assertion instead:

```python
payload = response.json()
assert payload["candidate_count"] == 0
assert payload["saved_paper_count"] == 0
assert payload["pending_candidate_count"] == 1
assert payload["confirmed_memory_count"] == 1
assert payload["known_doi_count"] == 0
assert len(payload["recent_logs"]) == 1
assert payload["recent_logs"][0]["content"] == "latest log"
assert payload["recent_logs"][0]["tags"] == ["graph"]
```

- [ ] **Step 5: Run the focused backend test again**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_api_mvp.py::test_memory_summary_returns_review_and_confirmed_counts -q
```

Expected: PASS

- [ ] **Step 6: Run the full backend API test file**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_api_mvp.py -q
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/src/main.py backend/src/tests/test_api_mvp.py
git commit -m "feat: expand memory summary contract"
```

### Task 2: Add Assistant Summary And Memory Summary Components

**Files:**
- Create: `frontend/src/components/AssistantSummaryPanel.vue`
- Create: `frontend/src/components/MemorySummaryCard.vue`
- Create: `frontend/src/components/__tests__/AssistantSummaryPanel.test.js`
- Create: `frontend/src/components/__tests__/MemorySummaryCard.test.js`
- Modify: `frontend/src/api.js`

- [ ] **Step 1: Write the failing assistant summary component test**

Create `frontend/src/components/__tests__/AssistantSummaryPanel.test.js`:

```javascript
import { describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";

import AssistantSummaryPanel from "../AssistantSummaryPanel.vue";

describe("AssistantSummaryPanel", () => {
  test("renders assistant route, message, next action, and notes", () => {
    const wrapper = mount(AssistantSummaryPanel, {
      props: {
        summary: {
          mode: "advanced",
          route: "advanced_search",
          coverage_score: 0.72,
          route_reason: "Existing knowledge overlaps with the query.",
          assistant_message: "Use local evidence and discovery together.",
          next_action: {
            type: "upload_pdf",
            message: "Review the recommended papers.",
            options: ["accept", "upload_pdf"],
          },
          suggested_user_actions: ["Review top papers", "Upload selected PDFs"],
          errors: [{ section: "memory", message: "memory unavailable" }],
        },
      },
    });

    const text = wrapper.text();
    expect(text).toContain("mode: advanced");
    expect(text).toContain("route: advanced_search");
    expect(text).toContain("72%");
    expect(text).toContain("Use local evidence and discovery together.");
    expect(text).toContain("Review the recommended papers.");
    expect(text).toContain("Review top papers");
    expect(text).toContain("Upload selected PDFs");
    expect(text).toContain("memory: memory unavailable");
  });

  test("stays hidden when no summary is available", () => {
    const wrapper = mount(AssistantSummaryPanel, {
      props: {
        summary: null,
      },
    });

    expect(wrapper.text()).not.toContain("Assistant Summary");
  });
});
```

- [ ] **Step 2: Write the failing memory summary card test**

Create `frontend/src/components/__tests__/MemorySummaryCard.test.js`:

```javascript
import { describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";

import MemorySummaryCard from "../MemorySummaryCard.vue";

describe("MemorySummaryCard", () => {
  test("renders the lightweight memory summary contract", () => {
    const wrapper = mount(MemorySummaryCard, {
      props: {
        summary: {
          pending_candidate_count: 2,
          confirmed_memory_count: 5,
          known_doi_count: 3,
          recent_logs: [{ content: "latest log", tags: ["graph"] }],
        },
        loading: false,
        error: "",
      },
    });

    const text = wrapper.text();
    expect(text).toContain("Pending review");
    expect(text).toContain("2");
    expect(text).toContain("Confirmed memory");
    expect(text).toContain("5");
    expect(text).toContain("Known DOIs");
    expect(text).toContain("3");
    expect(text).toContain("latest log");
  });

  test("renders loading and endpoint errors", () => {
    const loadingWrapper = mount(MemorySummaryCard, {
      props: {
        summary: null,
        loading: true,
        error: "",
      },
    });
    expect(loadingWrapper.text()).toContain("Loading memory summary...");

    const errorWrapper = mount(MemorySummaryCard, {
      props: {
        summary: null,
        loading: false,
        error: "memory summary unavailable",
      },
    });
    expect(errorWrapper.text()).toContain("memory summary unavailable");
  });
});
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/AssistantSummaryPanel.test.js src/components/__tests__/MemorySummaryCard.test.js
```

Expected: FAIL because both component files do not exist yet.

- [ ] **Step 4: Add the frontend API helper**

In `frontend/src/api.js`, add:

```javascript
export function getMemorySummary() {
  return request("/memory/summary");
}
```

The export block at the bottom should stay:

```javascript
export { API_BASE_URL };
```

- [ ] **Step 5: Implement the assistant summary component**

Create `frontend/src/components/AssistantSummaryPanel.vue`:

```vue
<template>
  <section v-if="summary" class="panel panel--full">
    <div class="panel__heading">
      <div>
        <h2>Assistant Summary</h2>
        <p>Route, confidence, and next-step guidance for the current assistant result.</p>
      </div>
      <span class="badge" :class="summary.mode === 'advanced' ? 'badge--active' : 'badge--muted'">
        mode: {{ summary.mode || "n/a" }}
      </span>
    </div>

    <div class="panel__section">
      <div class="section-title">
        <h3>Current Route</h3>
        <span class="meta">coverage: {{ coveragePercent }}</span>
      </div>
      <div class="kv-grid">
        <span>route: {{ summary.route || "n/a" }}</span>
      </div>
      <p v-if="summary.route_reason" class="hint">{{ summary.route_reason }}</p>
      <p v-if="summary.assistant_message" class="answer-block">{{ summary.assistant_message }}</p>
    </div>

    <div v-if="summary.next_action" class="panel__section">
      <div class="section-title">
        <h3>Next Action</h3>
        <span class="meta">{{ summary.next_action.type || "n/a" }}</span>
      </div>
      <p class="text-block">{{ summary.next_action.message }}</p>
      <div v-if="summary.next_action.options?.length" class="kv-grid">
        <span v-for="option in summary.next_action.options" :key="option">option: {{ option }}</span>
      </div>
    </div>

    <div v-if="summary.suggested_user_actions?.length" class="panel__section">
      <div class="section-title">
        <h3>Suggested Actions</h3>
      </div>
      <ul class="assistant-actions">
        <li v-for="action in summary.suggested_user_actions" :key="action">{{ action }}</li>
      </ul>
    </div>

    <div v-if="summary.errors?.length" class="panel__section">
      <div class="section-title">
        <h3>Workflow Notes</h3>
      </div>
      <ul class="stack-list">
        <li v-for="(workflowError, index) in summary.errors" :key="index" class="source-card">
          <strong>{{ workflowError.section || "workflow" }}:</strong> {{ workflowError.message }}
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  summary: {
    type: Object,
    default: null,
  },
});

const coveragePercent = computed(() => {
  if (typeof props.summary?.coverage_score !== "number") {
    return "n/a";
  }
  return `${Math.round(props.summary.coverage_score * 100)}%`;
});
</script>
```

- [ ] **Step 6: Implement the memory summary card**

Create `frontend/src/components/MemorySummaryCard.vue`:

```vue
<template>
  <section class="panel panel--full">
    <div class="panel__heading">
      <div>
        <h2>Memory Summary</h2>
        <p>Review-gated memory stays lightweight on the homepage.</p>
      </div>
      <span class="badge badge--muted">summary</span>
    </div>

    <div v-if="error" class="alert alert--warning">
      <strong>Memory summary error:</strong> {{ error }}
    </div>

    <p v-if="loading" class="empty-state">Loading memory summary...</p>

    <template v-else-if="summary">
      <div class="kv-grid">
        <span>Pending review: {{ summary.pending_candidate_count ?? 0 }}</span>
        <span>Confirmed memory: {{ summary.confirmed_memory_count ?? 0 }}</span>
        <span>Known DOIs: {{ summary.known_doi_count ?? 0 }}</span>
        <span>Saved papers: {{ summary.saved_paper_count ?? summary.candidate_count ?? 0 }}</span>
      </div>

      <div class="panel__section">
        <div class="section-title">
          <h3>Recent Logs</h3>
          <span class="meta">{{ summary.recent_logs?.length || 0 }} shown</span>
        </div>
        <ul v-if="summary.recent_logs?.length" class="stack-list">
          <li v-for="(log, index) in summary.recent_logs" :key="index" class="source-card">
            <p class="text-block">{{ log.content || "No log content." }}</p>
          </li>
        </ul>
        <p v-else class="empty-state">No recent logs recorded yet.</p>
      </div>
    </template>
  </section>
</template>

<script setup>
defineProps({
  summary: {
    type: Object,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: "",
  },
});
</script>
```

- [ ] **Step 7: Run the focused frontend tests again**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/AssistantSummaryPanel.test.js src/components/__tests__/MemorySummaryCard.test.js
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api.js frontend/src/components/AssistantSummaryPanel.vue frontend/src/components/MemorySummaryCard.vue frontend/src/components/__tests__/AssistantSummaryPanel.test.js frontend/src/components/__tests__/MemorySummaryCard.test.js
git commit -m "feat: add assistant and memory summary panels"
```

### Task 3: Re-Orchestrate ResearchWorkbench Around The Assistant-First Layout

**Files:**
- Modify: `frontend/src/components/ResearchWorkbench.vue`
- Modify: `frontend/src/components/AssistantWorkflowPanel.vue`
- Modify: `frontend/src/components/CandidateLifecyclePanel.vue`
- Modify: `frontend/src/components/QueryForm.vue`
- Modify: `frontend/src/components/__tests__/ResearchWorkbench.test.js`
- Modify: `frontend/src/components/__tests__/AssistantWorkflowPanel.test.js`

- [ ] **Step 1: Expand the workbench integration test first**

Replace `frontend/src/components/__tests__/ResearchWorkbench.test.js` with:

```javascript
import { describe, expect, test, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../../api", async () => {
  const actual = await vi.importActual("../../api");
  return {
    ...actual,
    getHealth: vi.fn().mockResolvedValue({ status: "ok" }),
    getCandidates: vi.fn().mockResolvedValue([]),
    getMemorySummary: vi.fn().mockResolvedValue({
      candidate_count: 0,
      saved_paper_count: 0,
      pending_candidate_count: 2,
      confirmed_memory_count: 5,
      known_doi_count: 3,
      recent_logs: [{ content: "latest log", tags: ["graph"] }],
    }),
    researchAssistant: vi.fn(),
    researchQuery: vi.fn(),
    acceptPaper: vi.fn(),
    uploadPdf: vi.fn(),
    embedPaper: vi.fn(),
  };
});

import { researchAssistant, researchQuery } from "../../api";
import ResearchWorkbench from "../ResearchWorkbench.vue";

const assistantResponse = {
  mode: "advanced",
  route: "advanced_search",
  coverage_score: 0.72,
  route_reason: "Existing knowledge has enough overlap with the query.",
  assistant_message: "I can search with local context and discovery together.",
  next_action: {
    type: "upload_pdf",
    message: "Review the recommended papers.",
    options: ["accept", "upload_pdf"],
  },
  suggested_user_actions: ["Review top papers", "Upload selected PDFs"],
  errors: [{ section: "memory", message: "memory unavailable" }],
  discovery: {
    enabled: true,
    candidates: [
      {
        paper: {
          paper_id: "assistant-paper",
          title: "Assistant discovery paper",
          authors: ["Ada Lovelace"],
          doi: "10.0000/assistant",
          venue: "Assistant Venue",
        },
        judgement: {
          final_score: 0.91,
          llm_relevance_score: 0.88,
          reason: "Assistant discovery reason",
        },
      },
    ],
    error: null,
  },
  knowledge: {
    enabled: true,
    answer: "Assistant knowledge answer",
    sources: [
      {
        paper_id: "assistant-source",
        chunk_index: 1,
        distance: 0.12,
        title: "Assistant source title",
        text: "Assistant source evidence",
      },
    ],
    error: null,
    mode: "assistant-grounded",
  },
  ideas: [],
};

const queryResponse = {
  discovery: {
    enabled: true,
    candidates: [
      {
        paper: {
          paper_id: "query-paper",
          title: "Legacy query discovery paper",
          authors: ["Grace Hopper"],
          doi: "10.0000/query",
          venue: "Query Venue",
        },
        judgement: {
          final_score: 0.75,
          llm_relevance_score: 0.7,
          reason: "Legacy query discovery reason",
        },
      },
    ],
    error: null,
  },
  knowledge: {
    enabled: true,
    answer: "Legacy query knowledge answer",
    sources: [
      {
        paper_id: "query-source",
        chunk_index: 2,
        distance: 0.34,
        title: "Legacy query source title",
        text: "Legacy query source evidence",
      },
    ],
    error: null,
    mode: "query-grounded",
  },
};

describe("ResearchWorkbench", () => {
  test("renders the assistant-first layout with memory summary and collapsed lifecycle", async () => {
    const wrapper = mount(ResearchWorkbench);
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain("Assistant Workflow");
    expect(text).toContain("Memory Summary");
    expect(text).toContain("Pending review: 2");
    expect(text).toContain("Confirmed memory: 5");
    expect(text).toContain("Research Query");
    expect(text).toContain("Saved Candidates & Lifecycle");
    expect(text).not.toContain("No saved candidates in SQLite yet.");
  });

  test("shows assistant summary and switches visible results to assistant output", async () => {
    researchAssistant.mockResolvedValueOnce(assistantResponse);
    const wrapper = mount(ResearchWorkbench);

    await wrapper.find("#assistant-query").setValue("assistant route");
    await wrapper.find("form.assistant-form").trigger("submit.prevent");
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain("Assistant Summary");
    expect(text).toContain("route: advanced_search");
    expect(text).toContain("72%");
    expect(text).toContain("Assistant knowledge answer");
    expect(text).toContain("Assistant discovery paper");
    expect(text).toContain("Results source: assistant");
  });

  test("preserves assistant results if the fallback query fails", async () => {
    researchAssistant.mockResolvedValueOnce(assistantResponse);
    researchQuery.mockRejectedValueOnce(new Error("query fallback failed"));
    const wrapper = mount(ResearchWorkbench);

    await wrapper.find("#assistant-query").setValue("assistant route");
    await wrapper.find("form.assistant-form").trigger("submit.prevent");
    await flushPromises();

    await wrapper.find("#query").setValue("legacy route");
    await wrapper.find("form.query-form").trigger("submit.prevent");
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain("query fallback failed");
    expect(text).toContain("Assistant knowledge answer");
    expect(text).toContain("Assistant discovery paper");
    expect(text).toContain("Results source: assistant");
  });

  test("switches back to research/query results after legacy query success", async () => {
    researchAssistant.mockResolvedValueOnce(assistantResponse);
    researchQuery.mockResolvedValueOnce(queryResponse);
    const wrapper = mount(ResearchWorkbench);

    await wrapper.find("#assistant-query").setValue("assistant route");
    await wrapper.find("form.assistant-form").trigger("submit.prevent");
    await flushPromises();

    await wrapper.find("#query").setValue("legacy route");
    await wrapper.find("form.query-form").trigger("submit.prevent");
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain("Results source: research/query");
    expect(text).toContain("Legacy query knowledge answer");
    expect(text).toContain("Legacy query discovery paper");
  });
});
```

- [ ] **Step 2: Tighten the assistant workflow panel test to cover summary handoff**

Update the response shape in `frontend/src/components/__tests__/AssistantWorkflowPanel.test.js` to include the summary fields but assert that the panel itself no longer renders `Next Action`, `Suggested Actions`, or `Workflow Notes`. Replace the render test with:

```javascript
test("renders the compact assistant workflow form response", async () => {
  const wrapper = mountPanel({
    props: {
      runAssistant: vi.fn().mockResolvedValue(assistantResponse),
    },
  });

  await wrapper.find("#assistant-query").setValue("local evidence with discovery");
  await wrapper.find("form.assistant-form").trigger("submit.prevent");

  const text = wrapper.text();
  expect(text).toContain("mode: advanced");
  expect(text).toContain("route: advanced_search");
  expect(text).toContain("72%");
  expect(text).toContain("I can search with local context and discovery together.");
  expect(text).not.toContain("Next Action");
  expect(text).not.toContain("Suggested Actions");
  expect(text).not.toContain("Workflow Notes");
});
```

- [ ] **Step 3: Run the focused frontend tests to verify they fail**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/ResearchWorkbench.test.js src/components/__tests__/AssistantWorkflowPanel.test.js
```

Expected: FAIL because the current workbench still renders lifecycle inline, does not fetch memory summary, and keeps the full assistant summary inside `AssistantWorkflowPanel`.

- [ ] **Step 4: Refactor the assistant workflow panel into an input-first surface**

In `frontend/src/components/AssistantWorkflowPanel.vue`, keep the form and endpoint error handling, but remove the in-panel rendering of `next_action`, `suggested_user_actions`, `errors`, and `ideas`. The success payload should still be emitted upward:

```vue
<template>
  <section id="assistant-workflow-panel" class="panel panel--full">
    <div class="panel__heading">
      <div>
        <h2>Assistant Workflow</h2>
        <p>Start with an assistant-guided research pass before dropping to direct query controls.</p>
      </div>
      <span class="badge" :class="isBusy ? 'badge--muted' : 'badge--active'">
        {{ isBusy ? "Running" : "Ready" }}
      </span>
    </div>

    <form class="assistant-form" @submit.prevent="submitAssistant">
      <!-- keep existing fields -->
    </form>

    <div v-if="error" class="alert alert--danger assistant-form__status">
      <strong>Assistant request failed:</strong> {{ error }}
    </div>

    <div v-if="response" class="panel__section">
      <div class="section-title">
        <h3>Latest Run</h3>
        <span class="meta">mode: {{ response.mode || "n/a" }}</span>
      </div>
      <div class="kv-grid">
        <span>route: {{ response.route || "n/a" }}</span>
        <span>coverage: {{ coveragePercent }}</span>
      </div>
      <p v-if="response.assistant_message" class="hint">{{ response.assistant_message }}</p>
    </div>
  </section>
</template>
```

- [ ] **Step 5: Rebuild `ResearchWorkbench.vue` around the assistant-first layout**

Update `frontend/src/components/ResearchWorkbench.vue` to:

```vue
<template>
  <main class="workbench-shell">
    <header class="topbar">
      <div>
        <h1>Research Workbench</h1>
        <p>Assistant-first research flow with direct query fallback and local lifecycle controls.</p>
      </div>
      <div class="status-cluster">
        <span class="badge" :class="healthBadgeClass">{{ healthLabel }}</span>
        <span class="meta">API base: {{ apiBaseUrl }}</span>
      </div>
    </header>

    <div v-if="healthError" class="alert alert--danger">
      <strong>Backend health check failed:</strong> {{ healthError }}
    </div>

    <div v-if="queryError" class="alert alert--danger">
      <strong>Search failed:</strong> {{ queryError }}
    </div>

    <div v-if="hasPartialFailure" class="alert alert--warning">
      <strong>Partial failure:</strong> one workflow section failed, but the other section may still be usable.
    </div>

    <AssistantWorkflowPanel :run-assistant="handleAssistant" @success="handleAssistantSuccess" />
    <AssistantSummaryPanel :summary="assistantSummary" />

    <p class="meta">Results source: {{ resultSourceLabel }}</p>
    <section class="workspace-grid">
      <KnowledgePanel :knowledge="knowledgeSection" />
      <DiscoveryPanel :discovery="discoverySection" :action-states="candidateActionStates" @accept="handleDiscoveryAccept" />
    </section>

    <section class="panel panel--full">
      <div class="panel__heading">
        <div>
          <h2>Research Query</h2>
          <p>Fallback path for direct `/research/query` calls when you want manual control.</p>
        </div>
      </div>
      <QueryForm :loading="queryLoading" @submit="handleQuery" />
    </section>

    <section class="panel panel--full">
      <div class="panel__heading">
        <div>
          <h2>Saved Candidates & Lifecycle</h2>
          <p>Persisted papers, PDF upload, and embedding stay out of the main result flow by default.</p>
        </div>
        <button class="button button--ghost" type="button" @click="isLifecycleOpen = !isLifecycleOpen">
          {{ isLifecycleOpen ? "Hide" : "Open" }}
        </button>
      </div>

      <p v-if="candidateActionHint" class="success-text">{{ candidateActionHint }}</p>

      <p v-if="!isLifecycleOpen && !candidates.length" class="empty-state">
        No saved papers yet. Accept a discovery candidate to start building your local research set.
      </p>

      <CandidateLifecyclePanel
        v-if="isLifecycleOpen"
        :candidates="candidates"
        :loading="candidatesLoading"
        :error="candidatesError"
        :action-states="candidateActionStates"
        :selected-files="selectedFiles"
        @accept="handleAccept"
        @upload="handleUpload"
        @embed="handleEmbed"
        @refresh="loadCandidates"
        @select-file="handleFileSelection"
      />
    </section>

    <MemorySummaryCard :summary="memorySummary" :loading="memorySummaryLoading" :error="memorySummaryError" />
    <IdeaAssistantPanel />
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";

import {
  API_BASE_URL,
  acceptPaper,
  embedPaper,
  getCandidates,
  getHealth,
  getMemorySummary,
  researchAssistant,
  researchQuery,
  uploadPdf,
} from "../api";
import AssistantSummaryPanel from "./AssistantSummaryPanel.vue";
import AssistantWorkflowPanel from "./AssistantWorkflowPanel.vue";
import CandidateLifecyclePanel from "./CandidateLifecyclePanel.vue";
import DiscoveryPanel from "./DiscoveryPanel.vue";
import IdeaAssistantPanel from "./IdeaAssistantPanel.vue";
import KnowledgePanel from "./KnowledgePanel.vue";
import MemorySummaryCard from "./MemorySummaryCard.vue";
import QueryForm from "./QueryForm.vue";

const assistantResponse = ref(null);
const queryResponse = ref(null);
const memorySummary = ref(null);
const memorySummaryLoading = ref(false);
const memorySummaryError = ref("");
const isLifecycleOpen = ref(false);
const candidateActionHint = ref("");

const assistantSummary = computed(() => {
  if (!assistantResponse.value) {
    return null;
  }
  return {
    mode: assistantResponse.value.mode,
    route: assistantResponse.value.route,
    coverage_score: assistantResponse.value.coverage_score,
    route_reason: assistantResponse.value.route_reason,
    assistant_message: assistantResponse.value.assistant_message,
    next_action: assistantResponse.value.next_action,
    suggested_user_actions: assistantResponse.value.suggested_user_actions,
    errors: assistantResponse.value.errors,
  };
});

async function loadMemorySummary() {
  memorySummaryLoading.value = true;
  memorySummaryError.value = "";
  try {
    memorySummary.value = await getMemorySummary();
  } catch (error) {
    memorySummaryError.value = error.message;
  } finally {
    memorySummaryLoading.value = false;
  }
}

onMounted(() => {
  loadHealth();
  loadCandidates();
  loadMemorySummary();
});

function handleAssistantSuccess(response) {
  assistantResponse.value = response;
  activeResultSource.value = "assistant";
}

async function handleDiscoveryAccept(candidate) {
  const paperId = candidate?.paper?.paper_id;
  if (!paperId || !candidate?.paper) {
    return;
  }

  await runCandidateAction(paperId, async () => {
    const result = await acceptPaper(paperId, {
      paper: candidate.paper,
      judgement: candidate.judgement || null,
    });
    candidateActionHint.value = "Paper saved. Open Saved Candidates to upload the PDF and continue embedding.";
    await loadMemorySummary();
    return `Saved and accepted: ${result.status}`;
  });
}
```

Keep the existing `runCandidateAction`, `loadCandidates`, and result-source logic, but preserve the last successful result if a new request fails.

- [ ] **Step 6: Simplify the lifecycle component for drawer use**

In `frontend/src/components/CandidateLifecyclePanel.vue`, remove the outer title/refresh heading because the parent drawer now owns the section heading. The template should begin:

```vue
<template>
  <div>
    <div class="lifecycle-toolbar">
      <button class="button button--ghost" type="button" @click="$emit('refresh')" :disabled="loading">
        Refresh
      </button>
    </div>

    <div v-if="error" class="alert alert--danger">
      <strong>Candidate load failed:</strong> {{ error }}
    </div>

    <p v-if="loading" class="empty-state">Loading candidates...</p>
    <p v-else-if="!candidates.length" class="empty-state">
      No saved papers yet. Accept a discovery candidate to start building your local research set.
    </p>

    <!-- keep the lifecycle card list -->
  </div>
</template>
```

- [ ] **Step 7: Make the query form read as a secondary path**

In `frontend/src/components/QueryForm.vue`, update the header copy:

```vue
<div class="query-form__header">
  <div>
    <h2>Direct Research Query</h2>
    <p>Fallback path: <code>POST /research/query</code></p>
  </div>
  <button class="button button--primary" type="submit" :disabled="loading">
    {{ loading ? "Searching..." : "Search" }}
  </button>
</div>
```

- [ ] **Step 8: Run the focused frontend tests again**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/ResearchWorkbench.test.js src/components/__tests__/AssistantWorkflowPanel.test.js
```

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/ResearchWorkbench.vue frontend/src/components/AssistantWorkflowPanel.vue frontend/src/components/CandidateLifecyclePanel.vue frontend/src/components/QueryForm.vue frontend/src/components/__tests__/ResearchWorkbench.test.js frontend/src/components/__tests__/AssistantWorkflowPanel.test.js
git commit -m "feat: restructure workbench around assistant-first flow"
```

### Task 4: Polish Layout, Wire Styles, And Run End-To-End Verification

**Files:**
- Modify: `frontend/src/styles.css`
- Run tests/build only

- [ ] **Step 1: Write the failing style/structure assertion**

Add this test to `frontend/src/components/__tests__/ResearchWorkbench.test.js`:

```javascript
test("keeps lifecycle collapsed until the user opens it", async () => {
  const wrapper = mount(ResearchWorkbench);
  await flushPromises();

  expect(wrapper.text()).toContain("Saved Candidates & Lifecycle");
  expect(wrapper.text()).not.toContain("Upload PDF");

  await wrapper.find("button").trigger("click");
  expect(wrapper.text()).toContain("Upload PDF");
});
```

If button lookup is too broad, replace it with:

```javascript
await wrapper.find("button.button--ghost").trigger("click");
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/ResearchWorkbench.test.js
```

Expected: FAIL until the drawer markup and visibility classes are finalized.

- [ ] **Step 3: Update global styles for the new layout**

In `frontend/src/styles.css`, add these sections:

```css
.workbench-shell {
  width: min(1400px, calc(100% - 32px));
  margin: 0 auto;
  padding: 24px 0 40px;
  display: grid;
  gap: 18px;
}

.workspace-grid {
  grid-template-columns: 1.1fr 0.9fr;
  margin-bottom: 0;
}

.panel--collapsed {
  padding-bottom: 16px;
}

.lifecycle-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.memory-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 16px;
  margin-top: 12px;
}

@media (max-width: 900px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .query-form__grid,
  .memory-summary-grid,
  .kv-grid {
    grid-template-columns: 1fr;
  }
}
```

Keep the existing color system and panel visual language intact.

- [ ] **Step 4: Add the missing class hooks to the new components**

If the styles from Step 3 need matching hooks, update:

- `MemorySummaryCard.vue` to render the metric area with `class="memory-summary-grid"`
- the lifecycle wrapper section in `ResearchWorkbench.vue` with `:class="['panel', 'panel--full', !isLifecycleOpen && 'panel--collapsed']"`

Use this exact panel wrapper:

```vue
<section :class="['panel', 'panel--full', !isLifecycleOpen && 'panel--collapsed']">
```

- [ ] **Step 5: Run the full frontend test suite**

Run:

```bash
cd frontend
npm test
```

Expected: PASS

- [ ] **Step 6: Run the frontend production build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS

- [ ] **Step 7: Run the backend tests touched by the summary contract**

Run:

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests/test_api_mvp.py -q
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/styles.css frontend/src/components/ResearchWorkbench.vue frontend/src/components/MemorySummaryCard.vue frontend/src/components/__tests__/ResearchWorkbench.test.js
git commit -m "style: polish assistant-first workbench layout"
```

## Self-Review

**Spec coverage**

- Assistant-first homepage structure: covered in Task 3
- Assistant summary split from the entry form: covered in Task 2 and Task 3
- `/research/query` fallback positioning: covered in Task 3
- Collapsed saved-candidates lifecycle: covered in Task 3 and Task 4
- Lightweight memory summary: covered in Task 1, Task 2, and Task 3
- Idea Assistant stays independent: preserved in Task 3 tests and markup
- Preserve last successful results on request failure: covered in Task 3 test and orchestration code

**Placeholder scan**

- No `TBD`, `TODO`, or “implement later” placeholders remain.
- Each code-changing step includes exact code or replacement content.
- Each verification step includes exact commands and expected outcomes.

**Type consistency**

- Memory summary contract uses `pending_candidate_count`, `confirmed_memory_count`, `known_doi_count`, `saved_paper_count`, and `recent_logs` consistently across backend tests, API helper usage, and frontend components.
- Result-source state remains `assistantResult`, `queryResult`, and `activeResultSource`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-27-research-workbench-assistant-first-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
