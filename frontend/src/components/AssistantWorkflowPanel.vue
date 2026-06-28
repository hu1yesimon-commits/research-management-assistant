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
        <h3>Latest Run</h3>
        <span class="meta">mode: {{ response.mode || "n/a" }}</span>
      </div>

      <div class="kv-grid">
        <span>route: {{ response.route || "n/a" }}</span>
        <span>coverage: {{ coveragePercent }}</span>
      </div>

      <p v-if="response.route_reason" class="hint">{{ response.route_reason }}</p>
      <p v-if="response.assistant_message" class="answer-block">{{ response.assistant_message }}</p>
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
