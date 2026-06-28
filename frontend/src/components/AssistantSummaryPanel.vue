<template>
  <section v-if="summary" class="panel panel--full">
    <div class="panel__heading">
      <div>
        <h2>Assistant Summary</h2>
        <p>Current assistant route, confidence, and follow-up guidance.</p>
      </div>
      <span class="badge" :class="summary.mode ? 'badge--active' : 'badge--muted'">
        {{ summary.mode ? `mode: ${summary.mode}` : "mode: n/a" }}
      </span>
    </div>

    <div class="panel__section">
      <div class="section-title">
        <h3>Workflow Route</h3>
        <span class="meta">coverage: {{ coveragePercent }}</span>
      </div>
      <div class="kv-grid">
        <span>route: {{ summary.route || "n/a" }}</span>
        <span>coverage: {{ coveragePercent }}</span>
      </div>
      <p v-if="summary.route_reason" class="hint">{{ summary.route_reason }}</p>
      <p v-if="summary.assistant_message" class="answer-block">{{ summary.assistant_message }}</p>
    </div>

    <div v-if="summary.next_action" class="panel__section">
      <div class="section-title">
        <h3>Next Action</h3>
        <span v-if="summary.next_action.type" class="meta">{{ summary.next_action.type }}</span>
      </div>
      <p class="text-block">{{ summary.next_action.message }}</p>
      <div v-if="summary.next_action.options?.length" class="kv-grid">
        <span v-for="option in summary.next_action.options" :key="option">option: {{ option }}</span>
      </div>
    </div>

    <div v-if="summary.suggested_user_actions?.length" class="panel__section">
      <div class="section-title">
        <h3>Suggested Actions</h3>
        <span class="meta">{{ summary.suggested_user_actions.length }} shown</span>
      </div>
      <ul class="stack-list">
        <li v-for="action in summary.suggested_user_actions" :key="action" class="source-card">
          {{ action }}
        </li>
      </ul>
    </div>

    <div v-if="summary.errors?.length" class="panel__section">
      <div class="section-title">
        <h3>Workflow Notes</h3>
        <span class="meta">{{ summary.errors.length }} shown</span>
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
