# Assistant Workflow Frontend Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-version frontend display for `POST /research/assistant` above the existing Research Workbench without replacing the current `/research/query` path.

**Architecture:** Add a focused `AssistantWorkflowPanel` that owns the assistant form and request lifecycle, then let `ResearchWorkbench` decide whether the visible knowledge/discovery panels should read from the latest assistant response or the legacy query response. Existing `KnowledgePanel`, `DiscoveryPanel`, lifecycle, and idea assistant paths remain intact.

**Tech Stack:** Vue 3, Vite, Vitest, `@vue/test-utils`, existing Fetch API wrapper in `frontend/src/api.js`.

---

## File Structure

- Create `frontend/src/components/AssistantWorkflowPanel.vue`
  - Owns first-version assistant input, loading/error state, compact workflow summary, next action, suggested actions, errors, and ideas display.
  - Emits `success` with the full assistant response after a successful request.
- Create `frontend/src/components/__tests__/AssistantWorkflowPanel.test.js`
  - Covers defaults, submit payload, successful render, endpoint error, workflow errors, and research intent hint.
- Modify `frontend/src/api.js`
  - Add `researchAssistant(payload)` using the existing `request()` helper.
- Modify `frontend/src/components/ResearchWorkbench.vue`
  - Import and render `AssistantWorkflowPanel` above `QueryForm`.
  - Add `assistantResponse` and `activeResultSource`.
  - Route visible `knowledgeSection` and `discoverySection` to either assistant or legacy query response.
  - Keep legacy query behavior usable.
- Create `frontend/src/components/__tests__/ResearchWorkbench.test.js`
  - Covers source switching between assistant and legacy query without exercising backend network calls.
- Modify `frontend/src/styles.css`
  - Add only focused assistant display styles, reusing existing panel, badge, alert, and stack patterns where possible.

## Task 1: Add Assistant API Helper

**Files:**
- Modify: `frontend/src/api.js`
- Test: `frontend/src/components/__tests__/AssistantWorkflowPanel.test.js` in Task 2 will exercise this through component behavior.

- [ ] **Step 1: Add the API helper**

Add this function after `researchQuery(payload)`:

```js
export function researchAssistant(payload) {
  return request("/research/assistant", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}
```

- [ ] **Step 2: Run the existing frontend tests**

Run:

```bash
cd frontend
npm test -- --run
```

Expected: existing tests still pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.js
git commit -m "feat: add research assistant frontend API helper"
```

## Task 2: Build AssistantWorkflowPanel With Tests

**Files:**
- Create: `frontend/src/components/AssistantWorkflowPanel.vue`
- Create: `frontend/src/components/__tests__/AssistantWorkflowPanel.test.js`

- [ ] **Step 1: Write the failing component tests**

Create `frontend/src/components/__tests__/AssistantWorkflowPanel.test.js`:

```js
import { describe, expect, test, vi } from "vitest";
import { mount } from "@vue/test-utils";

import AssistantWorkflowPanel from "../AssistantWorkflowPanel.vue";

const assistantResponse = {
  mode: "advanced",
  route: "advanced_search",
  coverage_score: 0.72,
  route_reason: "Existing knowledge has enough overlap with the query.",
  assistant_message: "I can search with local context and discovery together.",
  next_action: {
    type: "select_candidate",
    message: "Review the recommended papers.",
    options: ["accept", "upload_pdf"],
  },
  suggested_user_actions: ["Review top papers", "Upload selected PDFs"],
  discovery: {
    enabled: true,
    candidates: [],
    error: null,
  },
  knowledge: {
    enabled: true,
    answer: "Grounded answer",
    sources: [],
    error: null,
    mode: "grounded",
  },
  ideas: [
    {
      title: "Try a smaller validation slice",
      rationale: "It reduces experiment cost.",
      suggested_validation_metric: "accuracy@10",
      next_small_experiment: "Run one baseline comparison.",
    },
  ],
  errors: [{ section: "memory", message: "memory unavailable" }],
};

describe("AssistantWorkflowPanel", () => {
  test("uses assistant-friendly defaults", () => {
    const wrapper = mount(AssistantWorkflowPanel, {
      props: {
        runAssistant: vi.fn(),
      },
    });

    expect(wrapper.find("#assistant-intent").element.value).toBe("auto");
    expect(wrapper.find("#assistant-top-k").element.value).toBe("5");
  });

  test("submits the current assistant payload and emits success", async () => {
    const runAssistant = vi.fn().mockResolvedValue(assistantResponse);
    const wrapper = mount(AssistantWorkflowPanel, {
      props: {
        runAssistant,
      },
    });

    await wrapper.find("#assistant-query").setValue("retrieval memory for research agents");
    await wrapper.find("#assistant-intent").setValue("search");
    await wrapper.find("#assistant-top-k").setValue(3);
    await wrapper.find("form").trigger("submit");

    expect(runAssistant).toHaveBeenCalledWith({
      query: "retrieval memory for research agents",
      intent: "search",
      top_k: 3,
    });
    expect(wrapper.emitted("success")).toEqual([[assistantResponse]]);
  });

  test("renders workflow summary, next action, errors, and ideas after success", async () => {
    const wrapper = mount(AssistantWorkflowPanel, {
      props: {
        runAssistant: vi.fn().mockResolvedValue(assistantResponse),
      },
    });

    await wrapper.find("#assistant-query").setValue("agentic rag");
    await wrapper.find("form").trigger("submit");

    expect(wrapper.text()).toContain("advanced");
    expect(wrapper.text()).toContain("advanced_search");
    expect(wrapper.text()).toContain("72%");
    expect(wrapper.text()).toContain("I can search with local context");
    expect(wrapper.text()).toContain("Review the recommended papers.");
    expect(wrapper.text()).toContain("memory unavailable");
    expect(wrapper.text()).toContain("Try a smaller validation slice");
  });

  test("shows endpoint errors without emitting success", async () => {
    const runAssistant = vi.fn().mockRejectedValue(new Error("assistant failed"));
    const wrapper = mount(AssistantWorkflowPanel, {
      props: {
        runAssistant,
      },
    });

    await wrapper.find("#assistant-query").setValue("agent workflow");
    await wrapper.find("form").trigger("submit");

    expect(wrapper.text()).toContain("assistant failed");
    expect(wrapper.emitted("success")).toBeUndefined();
  });

  test("shows research intent hint without adding a structured log form", async () => {
    const wrapper = mount(AssistantWorkflowPanel, {
      props: {
        runAssistant: vi.fn(),
      },
    });

    await wrapper.find("#assistant-intent").setValue("research");

    expect(wrapper.text()).toContain("Structured experiment logs stay in the Idea Assistant section below");
  });
});
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/AssistantWorkflowPanel.test.js
```

Expected: FAIL because `AssistantWorkflowPanel.vue` does not exist yet.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/AssistantWorkflowPanel.vue`:

```vue
<template>
  <section class="panel assistant-panel">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">Assistant Workflow</p>
        <h2>LangGraph route preview</h2>
      </div>
      <span v-if="response" class="badge badge--active">source: assistant</span>
      <span v-else class="badge badge--muted">source: idle</span>
    </div>

    <form class="assistant-form" @submit.prevent="handleSubmit">
      <label for="assistant-query">
        Research query
        <textarea
          id="assistant-query"
          v-model="query"
          rows="3"
          placeholder="Ask for papers, local knowledge, or next research ideas"
          required
        />
      </label>

      <div class="assistant-controls">
        <label for="assistant-intent">
          Intent
          <select id="assistant-intent" v-model="intent">
            <option value="auto">auto</option>
            <option value="search">search</option>
            <option value="research">research</option>
          </select>
        </label>

        <label for="assistant-top-k">
          Top K
          <input id="assistant-top-k" v-model.number="topK" type="number" min="1" max="20" />
        </label>

        <button type="submit" class="primary-button" :disabled="loading">
          {{ loading ? "Running..." : "Run Assistant" }}
        </button>
      </div>
    </form>

    <div v-if="intent === 'research'" class="alert alert--info assistant-hint">
      Structured experiment logs stay in the Idea Assistant section below for this version.
    </div>

    <div v-if="endpointError" class="alert alert--danger">
      <strong>Assistant failed:</strong> {{ endpointError }}
    </div>

    <div v-if="response" class="assistant-result">
      <div class="assistant-route-grid">
        <div>
          <span class="meta">Mode</span>
          <strong>{{ response.mode || "unknown" }}</strong>
        </div>
        <div>
          <span class="meta">Route</span>
          <strong>{{ response.route || "unknown" }}</strong>
        </div>
        <div>
          <span class="meta">Coverage</span>
          <strong>{{ coverageLabel }}</strong>
        </div>
      </div>

      <p v-if="response.route_reason" class="assistant-note">{{ response.route_reason }}</p>
      <p v-if="response.assistant_message" class="assistant-message">{{ response.assistant_message }}</p>

      <div v-if="response.next_action" class="assistant-next-action">
        <span class="meta">Next action</span>
        <strong>{{ response.next_action.type || "next" }}</strong>
        <p v-if="response.next_action.message">{{ response.next_action.message }}</p>
        <div v-if="nextActionOptions.length" class="tag-row">
          <span v-for="option in nextActionOptions" :key="option" class="tag">{{ option }}</span>
        </div>
      </div>

      <div v-if="suggestedActions.length" class="assistant-section">
        <h3>Suggested actions</h3>
        <ul>
          <li v-for="action in suggestedActions" :key="action">{{ action }}</li>
        </ul>
      </div>

      <div v-if="workflowErrors.length" class="alert alert--warning">
        <strong>Workflow notes:</strong>
        <ul>
          <li v-for="error in workflowErrors" :key="`${error.section}-${error.message}`">
            {{ error.section }}: {{ error.message }}
          </li>
        </ul>
      </div>

      <div v-if="ideas.length" class="assistant-section">
        <h3>Idea options</h3>
        <article v-for="idea in ideas" :key="idea.title" class="assistant-idea">
          <strong>{{ idea.title }}</strong>
          <p v-if="idea.rationale">{{ idea.rationale }}</p>
          <p v-if="idea.suggested_validation_metric" class="meta">
            Metric: {{ idea.suggested_validation_metric }}
          </p>
          <p v-if="idea.next_small_experiment" class="meta">
            Next: {{ idea.next_small_experiment }}
          </p>
        </article>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";

import { researchAssistant } from "../api";

const props = defineProps({
  runAssistant: {
    type: Function,
    default: researchAssistant,
  },
});

const emit = defineEmits(["success"]);

const query = ref("");
const intent = ref("auto");
const topK = ref(5);
const loading = ref(false);
const endpointError = ref("");
const response = ref(null);

const coverageLabel = computed(() => {
  const value = response.value?.coverage_score;
  if (typeof value !== "number") {
    return "n/a";
  }
  return `${Math.round(value * 100)}%`;
});

const nextActionOptions = computed(() => {
  return response.value?.next_action?.options || [];
});

const suggestedActions = computed(() => {
  return response.value?.suggested_user_actions || [];
});

const workflowErrors = computed(() => {
  return response.value?.errors || [];
});

const ideas = computed(() => {
  return response.value?.ideas || [];
});

async function handleSubmit() {
  loading.value = true;
  endpointError.value = "";

  try {
    const payload = {
      query: query.value.trim(),
      intent: intent.value,
      top_k: Number(topK.value) || 5,
    };
    const result = await props.runAssistant(payload);
    response.value = result;
    emit("success", result);
  } catch (error) {
    endpointError.value = error.message;
  } finally {
    loading.value = false;
  }
}
</script>
```

- [ ] **Step 4: Run the component test and verify it passes**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/AssistantWorkflowPanel.test.js
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AssistantWorkflowPanel.vue frontend/src/components/__tests__/AssistantWorkflowPanel.test.js
git commit -m "feat: add assistant workflow panel"
```

## Task 3: Wire Assistant Results Into ResearchWorkbench

**Files:**
- Modify: `frontend/src/components/ResearchWorkbench.vue`
- Create: `frontend/src/components/__tests__/ResearchWorkbench.test.js`

- [ ] **Step 1: Write the failing ResearchWorkbench test**

Create `frontend/src/components/__tests__/ResearchWorkbench.test.js`:

```js
import { describe, expect, test, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

import ResearchWorkbench from "../ResearchWorkbench.vue";

vi.mock("../../api", () => ({
  API_BASE_URL: "http://test.local",
  acceptPaper: vi.fn(),
  embedPaper: vi.fn(),
  getCandidates: vi.fn().mockResolvedValue([]),
  getHealth: vi.fn().mockResolvedValue({ status: "ok" }),
  researchQuery: vi.fn().mockResolvedValue({
    discovery: {
      enabled: true,
      candidates: [
        {
          paper: {
            paper_id: "legacy-1",
            title: "Legacy Query Paper",
          },
          judgement: {},
        },
      ],
      error: null,
    },
    knowledge: {
      enabled: true,
      answer: "Legacy answer",
      sources: [],
      error: null,
      mode: "grounded",
    },
  }),
  researchAssistant: vi.fn().mockResolvedValue({
    mode: "advanced",
    route: "advanced_search",
    coverage_score: 0.75,
    route_reason: "assistant route",
    assistant_message: "assistant result",
    next_action: null,
    suggested_user_actions: [],
    discovery: {
      enabled: true,
      candidates: [
        {
          paper: {
            paper_id: "assistant-1",
            title: "Assistant Paper",
          },
          judgement: {},
        },
      ],
      error: null,
    },
    knowledge: {
      enabled: true,
      answer: "Assistant answer",
      sources: [],
      error: null,
      mode: "grounded",
    },
    ideas: [],
    errors: [],
  }),
  uploadPdf: vi.fn(),
}));

describe("ResearchWorkbench", () => {
  test("switches visible knowledge and discovery to assistant after assistant success", async () => {
    const wrapper = mount(ResearchWorkbench);
    await flushPromises();

    await wrapper.find("#assistant-query").setValue("agent workflow");
    await wrapper.find(".assistant-form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("Results source: assistant");
    expect(wrapper.text()).toContain("Assistant Paper");
    expect(wrapper.text()).toContain("Assistant answer");
  });

  test("legacy query remains usable and switches visible result source back", async () => {
    const wrapper = mount(ResearchWorkbench);
    await flushPromises();

    await wrapper.find("#assistant-query").setValue("agent workflow");
    await wrapper.find(".assistant-form").trigger("submit");
    await flushPromises();

    await wrapper.find("#query").setValue("legacy workflow");
    await wrapper.findComponent({ name: "QueryForm" }).find("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("Results source: research/query");
    expect(wrapper.text()).toContain("Legacy Query Paper");
    expect(wrapper.text()).toContain("Legacy answer");
  });
});
```

- [ ] **Step 2: Run the new workbench test and verify it fails**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/ResearchWorkbench.test.js
```

Expected: FAIL because `ResearchWorkbench` is not wired to `AssistantWorkflowPanel` yet.

- [ ] **Step 3: Update ResearchWorkbench imports**

In `frontend/src/components/ResearchWorkbench.vue`, add `researchAssistant` to the API import and import the new component:

```js
import {
  API_BASE_URL,
  acceptPaper,
  embedPaper,
  getCandidates,
  getHealth,
  researchAssistant,
  researchQuery,
  uploadPdf,
} from "../api";
import AssistantWorkflowPanel from "./AssistantWorkflowPanel.vue";
```

- [ ] **Step 4: Add assistant state and active result routing**

Replace the current response refs and section computeds with:

```js
const queryResponse = ref(null);
const assistantResponse = ref(null);
const activeResultSource = ref("query");
```

Then replace `discoverySection` and `knowledgeSection` with:

```js
const activeResponse = computed(() => {
  if (activeResultSource.value === "assistant") {
    return assistantResponse.value;
  }
  return queryResponse.value;
});

const discoverySection = computed(() => activeResponse.value?.discovery || defaultDiscoverySection);
const knowledgeSection = computed(() => activeResponse.value?.knowledge || defaultKnowledgeSection);

const resultSourceLabel = computed(() => {
  return activeResultSource.value === "assistant" ? "assistant" : "research/query";
});
```

- [ ] **Step 5: Add assistant handlers**

Add these functions near `handleQuery`:

```js
async function handleAssistant(payload) {
  return researchAssistant(payload);
}

function handleAssistantSuccess(response) {
  assistantResponse.value = response;
  activeResultSource.value = "assistant";
}
```

Update `handleQuery(payload)` so successful legacy queries switch the source back:

```js
async function handleQuery(payload) {
  queryLoading.value = true;
  queryError.value = "";

  try {
    queryResponse.value = await researchQuery(payload);
    activeResultSource.value = "query";
  } catch (error) {
    queryError.value = error.message;
  } finally {
    queryLoading.value = false;
  }
}
```

- [ ] **Step 6: Render the assistant panel and source label**

In the template, render `AssistantWorkflowPanel` above `QueryForm`:

```vue
<AssistantWorkflowPanel :run-assistant="handleAssistant" @success="handleAssistantSuccess" />
```

Add a compact source label immediately before the workspace grid:

```vue
<div class="result-source-row">
  <span class="meta">Results source: {{ resultSourceLabel }}</span>
</div>
```

- [ ] **Step 7: Run the workbench test and verify it passes**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/ResearchWorkbench.test.js
```

Expected: PASS.

- [ ] **Step 8: Run all frontend tests**

Run:

```bash
cd frontend
npm test -- --run
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/ResearchWorkbench.vue frontend/src/components/__tests__/ResearchWorkbench.test.js
git commit -m "feat: wire assistant workflow into workbench"
```

## Task 4: Add Focused Assistant Styles And Build Verification

**Files:**
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add focused CSS**

Append these styles near the existing panel/form styles:

```css
.assistant-panel {
  display: grid;
  gap: 16px;
}

.assistant-form {
  display: grid;
  gap: 14px;
}

.assistant-controls {
  display: grid;
  grid-template-columns: minmax(140px, 1fr) minmax(96px, 120px) auto;
  gap: 12px;
  align-items: end;
}

.assistant-route-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.assistant-route-grid > div,
.assistant-next-action,
.assistant-idea {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  background: var(--surface-muted);
}

.assistant-result,
.assistant-section {
  display: grid;
  gap: 12px;
}

.assistant-message {
  font-size: 1rem;
  line-height: 1.6;
}

.assistant-note,
.assistant-hint {
  margin: 0;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag {
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 8px;
  color: var(--text-muted);
  font-size: 0.82rem;
}

.result-source-row {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 720px) {
  .assistant-controls,
  .assistant-route-grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 2: Run all frontend tests**

Run:

```bash
cd frontend
npm test -- --run
```

Expected: PASS.

- [ ] **Step 3: Run production build**

Run:

```bash
cd frontend
npm run build
```

Expected: build completes successfully.

- [ ] **Step 4: Optional browser smoke**

Run:

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

Open the local URL in the in-app browser and verify:

- Assistant panel is above legacy query form.
- The panel fits on desktop width and mobile width.
- Assistant success switches result source to `assistant`.
- Legacy query success switches result source to `research/query`.
- Existing candidate lifecycle and idea assistant sections remain visible.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles.css
git commit -m "style: polish assistant workflow display"
```

## Final Verification

- [ ] Run:

```bash
cd frontend
npm test -- --run
npm run build
```

Expected:

- Vitest passes.
- Vite build completes.

- [ ] Check backend contract has not been changed:

```bash
git diff -- backend/src
```

Expected: no backend source changes for this frontend display slice.

- [ ] Review `git status --short`.

Expected:

- Only intended frontend files are modified or committed.
- `.superpowers/` mockup artifacts are not staged.

## Review Points For User

The user should personally review these points before presenting the project:

- Why the first frontend version is a top Assistant Workflow panel instead of a full chat UI.
- How `activeResultSource` keeps `/research/assistant` and `/research/query` both explainable.
- Why `discovery` and `knowledge` are reused in existing panels instead of duplicated.
- What is intentionally not implemented yet: multi-turn history, checkpoint UI, SSE, MCP UI, and `next_action` auto-continuation.
