<template>
  <section class="panel panel--full">
    <div class="panel__heading">
      <div>
        <h2>Agent Trace</h2>
        <p>Bounded plan and typed run outcomes for the latest default-session turn.</p>
      </div>
      <span class="badge" :class="plan ? 'badge--active' : 'badge--muted'">
        {{ plan ? `Plan: ${plan.plan_type}` : "No trace yet" }}
      </span>
    </div>

    <p v-if="plan" class="text-block">{{ plan.goal }}</p>
    <p v-else class="empty-state">Run a session turn to capture the latest bounded plan and agent outcomes.</p>

    <details v-if="hasDetails" class="trace-details" :open="isOpen">
      <summary @click.prevent="isOpen = !isOpen">Show latest trace details</summary>

      <div v-if="isOpen" class="panel__section">
        <div class="section-title">
          <h3>Agent Runs</h3>
        </div>
        <ul class="stack-list">
          <li v-for="(run, index) in agentRuns" :key="`${run.agent_name}-${run.action}-${index}`" class="source-card">
            <div class="card-title-row">
              <strong>{{ run.agent_name }}</strong>
              <span class="status-pill">{{ run.status }}</span>
            </div>
            <p class="hint">{{ run.action }}</p>
          </li>
        </ul>
      </div>

      <div v-if="isOpen && errors.length" class="panel__section">
        <div class="section-title">
          <h3>Typed Errors</h3>
        </div>
        <ul class="stack-list">
          <li v-for="(error, index) in errors" :key="`${error.agent_name}-${error.stage}-${index}`" class="source-card">
            <strong>{{ error.agent_name }}: {{ error.message }}</strong>
            <p class="hint">stage: {{ error.stage }}</p>
          </li>
        </ul>
      </div>
    </details>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  plan: {
    type: Object,
    default: null,
  },
  agentRuns: {
    type: Array,
    default: () => [],
  },
  errors: {
    type: Array,
    default: () => [],
  },
});

const hasDetails = computed(() => props.agentRuns.length || props.errors.length);
const isOpen = ref(false);
</script>
