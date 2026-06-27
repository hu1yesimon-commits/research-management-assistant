<template>
  <section id="assistant-workflow-panel" class="panel panel--full">
    <div class="panel__heading">
      <div>
        <h2>Assistant Workflow</h2>
        <p>Single-turn routing across local knowledge and paper discovery.</p>
      </div>
      <span class="badge" :class="isBusy ? 'badge--muted' : 'badge--active'">
        {{ isBusy ? "Running" : "Ready" }}
      </span>
    </div>

    <form class="assistant-form" @submit.prevent="submitAssistant">
      <label class="field assistant-form__full">
        <span>Query</span>
        <textarea
          id="assistant-query"
          v-model.trim="form.query"
          rows="4"
          placeholder="Find papers and local evidence for a research question"
        />
      </label>

      <div class="assistant-form__controls">
        <label class="field">
          <span>Intent</span>
          <select id="assistant-intent" v-model="form.intent">
            <option value="auto">Auto</option>
            <option value="search">Search</option>
            <option value="research">Research</option>
          </select>
        </label>

        <label class="field">
          <span>Top K</span>
          <input id="assistant-top-k" v-model.number="form.top_k" type="number" min="1" max="20" />
        </label>

        <button class="button button--primary" type="submit" :disabled="isSubmitDisabled">
          {{ isBusy ? "Running..." : "Run assistant" }}
        </button>
      </div>

      <p v-if="form.intent === 'research'" class="hint">
        Structured experiment logs stay in the Idea Assistant section below
      </p>
    </form>

    <div v-if="error" class="alert alert--danger assistant-form__status">
      <strong>Assistant request failed:</strong> {{ error }}
    </div>

    <div v-if="response" class="panel__section">
      <div class="section-title">
        <h3>Workflow Route</h3>
        <span class="meta">mode: {{ response.mode || "n/a" }}</span>
      </div>

      <div class="kv-grid">
        <span>route: {{ response.route || "n/a" }}</span>
        <span>coverage: {{ coveragePercent }}</span>
      </div>

      <p v-if="response.route_reason" class="hint">{{ response.route_reason }}</p>
      <p v-if="response.assistant_message" class="answer-block">{{ response.assistant_message }}</p>
    </div>

    <div v-if="response?.next_action" class="panel__section">
      <div class="section-title">
        <h3>Next Action</h3>
        <span v-if="response.next_action.type" class="meta">{{ response.next_action.type }}</span>
      </div>
      <p class="text-block">{{ response.next_action.message }}</p>
      <div v-if="response.next_action.options?.length" class="kv-grid">
        <span v-for="option in response.next_action.options" :key="option">option: {{ option }}</span>
      </div>
    </div>

    <div v-if="response?.suggested_user_actions?.length" class="panel__section">
      <div class="section-title">
        <h3>Suggested Actions</h3>
        <span class="meta">{{ response.suggested_user_actions.length }} action{{ response.suggested_user_actions.length === 1 ? "" : "s" }}</span>
      </div>
      <ul class="assistant-actions">
        <li v-for="action in response.suggested_user_actions" :key="action">{{ action }}</li>
      </ul>
    </div>

    <div v-if="response?.errors?.length" class="panel__section">
      <div class="section-title">
        <h3>Workflow Notes</h3>
        <span class="meta">{{ response.errors.length }} note{{ response.errors.length === 1 ? "" : "s" }}</span>
      </div>
      <ul class="stack-list">
        <li v-for="(workflowError, errorIndex) in response.errors" :key="errorIndex" class="source-card">
          <strong>{{ workflowError.stage || workflowError.section || "workflow" }}:</strong> {{ workflowError.message }}
        </li>
      </ul>
    </div>

    <div v-if="response?.ideas?.length" class="panel__section">
      <div class="section-title">
        <h3>Ideas</h3>
        <span class="meta">{{ response.ideas.length }} returned</span>
      </div>

      <ul class="stack-list">
        <li v-for="(idea, ideaIndex) in response.ideas" :key="idea.title + '-' + ideaIndex" class="idea-card">
          <div class="card-title-row">
            <h4>{{ idea.title }}</h4>
            <span class="meta">Idea {{ ideaIndex + 1 }}</span>
          </div>
          <p class="text-block">{{ idea.rationale }}</p>
          <div class="kv-grid">
            <span>Metric: {{ idea.suggested_validation_metric || "n/a" }}</span>
            <span>Next step: {{ idea.next_small_experiment || "n/a" }}</span>
          </div>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup>
import { computed, reactive, ref } from "vue";

import { researchAssistant } from "../api";

const props = defineProps({
  runAssistant: {
    type: Function,
    default: researchAssistant,
  },
});

const emit = defineEmits(["success"]);

const form = reactive({
  query: "",
  intent: "auto",
  top_k: 5,
});

const isBusy = ref(false);
const error = ref("");
const response = ref(null);

const coveragePercent = computed(() => {
  if (typeof response.value?.coverage_score !== "number") {
    return "n/a";
  }
  return `${Math.round(response.value.coverage_score * 100)}%`;
});

const isSubmitDisabled = computed(() => isBusy.value || !form.query || form.intent === "research");

async function submitAssistant() {
  if (form.intent === "research") {
    return;
  }

  isBusy.value = true;
  error.value = "";
  response.value = null;

  try {
    const result = await props.runAssistant({
      query: form.query,
      intent: form.intent,
      top_k: Number(form.top_k),
    });
    response.value = result;
    emit("success", result);
  } catch (requestError) {
    error.value = requestError.message || "Assistant request failed";
  } finally {
    isBusy.value = false;
  }
}
</script>

<style scoped>
.assistant-form {
  margin-top: 16px;
}

.assistant-form__full {
  display: block;
}

.assistant-form__controls {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 14px;
  margin-top: 16px;
}

.assistant-form__status {
  margin-top: 16px;
}

.assistant-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.assistant-actions li {
  color: var(--text-muted);
  font-size: 0.86rem;
}

.idea-card + .idea-card {
  margin-top: 14px;
}
</style>
