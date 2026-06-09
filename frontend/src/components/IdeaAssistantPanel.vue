<template>
  <section id="idea-assistant-panel" class="panel panel--full">
    <div class="panel__heading">
      <div>
        <h2>Idea Assistant</h2>
        <p>Structured experiment logs in, deterministic idea options out. This stays inside the workbench.</p>
      </div>
      <span class="badge" :class="isBusy ? 'badge--muted' : 'badge--active'">
        {{ isBusy ? "Generating" : "Ready" }}
      </span>
    </div>

    <form class="idea-form" @submit.prevent="submitIdeas">
      <div class="idea-form__grid">
        <label class="field">
          <span>Task</span>
          <input id="idea-task" v-model.trim="form.task" type="text" placeholder="defect classification" />
        </label>

        <label class="field">
          <span>Model</span>
          <input id="idea-model" v-model.trim="form.model" type="text" placeholder="1D-CNN" />
        </label>

        <label class="field">
          <span>Dataset</span>
          <input id="idea-dataset" v-model.trim="form.dataset" type="text" placeholder="bearing fault dataset" />
        </label>

        <label class="field">
          <span>Metric problem</span>
          <input
            id="idea-metric-problem"
            v-model.trim="form.metric_problem"
            type="text"
            placeholder="minority class PRAUC is low"
          />
        </label>

        <label class="field idea-form__full">
          <span>Tried methods</span>
          <textarea
            id="idea-tried-methods"
            v-model="form.tried_methods"
            rows="3"
            placeholder="class weighting, focal loss"
          />
        </label>

        <label class="field idea-form__full">
          <span>Observation</span>
          <textarea
            id="idea-observation"
            v-model.trim="form.observation"
            rows="3"
            placeholder="recall improves but precision collapses"
          />
        </label>

        <label class="field idea-form__full">
          <span>Goal</span>
          <textarea
            id="idea-goal"
            v-model.trim="form.goal"
            rows="3"
            placeholder="improve PRAUC without making model too heavy"
          />
        </label>
      </div>

      <div class="idea-form__controls">
        <label class="checkbox">
          <input id="save-log" v-model="form.save_log" type="checkbox" />
          <span>Save log</span>
        </label>

        <label class="checkbox">
          <input id="include-discovery" v-model="form.include_discovery" type="checkbox" />
          <span>Include discovery</span>
        </label>

        <label class="field idea-form__count">
          <span>Idea count</span>
          <select id="idea-count" v-model.number="form.idea_count">
            <option :value="3">3</option>
            <option :value="4">4</option>
            <option :value="5">5</option>
          </select>
        </label>

        <button class="button button--primary" type="submit" :disabled="isBusy">
          {{ isBusy ? "Generating ideas..." : "Recommend ideas" }}
        </button>
      </div>
    </form>

    <div v-if="error" class="alert alert--danger idea-form__status">
      <strong>Idea request failed:</strong> {{ error }}
    </div>

    <div v-if="result" class="panel__section">
      <div class="section-title">
        <h3>Recommendations</h3>
        <span class="meta">mode: {{ result.mode || "n/a" }}</span>
      </div>

      <p v-if="result.query" class="hint">Query: {{ result.query }}</p>
      <p v-if="result.log_id" class="hint">log_id: {{ result.log_id }}</p>
      <p v-if="result.discovery?.error" class="error-text">Discovery error: {{ result.discovery.error }}</p>
      <p v-if="result.knowledge?.error" class="error-text">Knowledge error: {{ result.knowledge.error }}</p>

      <p v-if="!result.ideas?.length" class="empty-state">No ideas returned.</p>

      <ul v-else class="stack-list">
        <li v-for="(idea, ideaIndex) in result.ideas" :key="idea.title + '-' + ideaIndex" class="idea-card">
          <div class="card-title-row">
            <h4>{{ idea.title }}</h4>
            <span class="meta">Idea {{ ideaIndex + 1 }}</span>
          </div>

          <p class="text-block">{{ idea.rationale }}</p>

          <div class="kv-grid">
            <span>Expected benefit: {{ idea.expected_benefit }}</span>
            <span>Risk: {{ idea.risk }}</span>
            <span>Metric: {{ idea.suggested_validation_metric }}</span>
            <span>Next step: {{ idea.next_small_experiment }}</span>
          </div>

          <div class="idea-form__evidence">
            <h5>Supporting evidence</h5>
            <p v-if="!idea.supporting_evidence?.length" class="empty-state">No supporting evidence returned.</p>
            <ul v-else class="stack-list">
              <li
                v-for="(evidence, evidenceIndex) in idea.supporting_evidence"
                :key="idea.title + '-evidence-' + evidenceIndex"
                class="source-card"
              >
                <div class="card-title-row">
                  <h4>{{ evidence.title || evidence.paper_id || "Evidence item" }}</h4>
                  <span class="meta">{{ evidence.source_type }}</span>
                </div>

                <div class="kv-grid">
                  <span>paper_id: {{ evidence.paper_id || "n/a" }}</span>
                  <span>chunk_index: {{ evidence.chunk_index ?? "n/a" }}</span>
                  <span>distance: {{ formatDistance(evidence.distance) }}</span>
                  <span>vector_ref: {{ evidence.vector_ref || "n/a" }}</span>
                </div>

                <p v-if="evidence.text" class="text-block">{{ evidence.text }}</p>
              </li>
            </ul>
          </div>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup>
import { computed, reactive, ref } from "vue";

import { recommendIdeas } from "../api";

const form = reactive({
  task: "",
  model: "",
  dataset: "",
  metric_problem: "",
  tried_methods: "",
  observation: "",
  goal: "",
  save_log: true,
  include_discovery: false,
  idea_count: 3,
});

const isBusy = ref(false);
const error = ref("");
const result = ref(null);

const experimentLog = computed(() => ({
  task: form.task,
  model: form.model,
  dataset: form.dataset,
  metric_problem: form.metric_problem,
  tried_methods: parseMultilineList(form.tried_methods),
  observation: form.observation,
  goal: form.goal,
}));

async function submitIdeas() {
  isBusy.value = true;
  error.value = "";

  try {
    result.value = await recommendIdeas({
      experiment_log: experimentLog.value,
      save_log: form.save_log,
      include_discovery: form.include_discovery,
      idea_count: form.idea_count,
    });
  } catch (requestError) {
    error.value = requestError.message;
  } finally {
    isBusy.value = false;
  }
}

function parseMultilineList(value) {
  return String(value)
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatDistance(value) {
  return typeof value === "number" ? value.toFixed(4) : "n/a";
}
</script>

<style scoped>
.idea-form {
  margin-top: 16px;
}

.idea-form__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.idea-form__full {
  grid-column: 1 / -1;
}

.idea-form__controls {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 14px;
  margin-top: 16px;
}

.idea-form__count {
  min-width: 120px;
}

.idea-form__status {
  margin-top: 16px;
}

.idea-form__evidence {
  margin-top: 14px;
}

.idea-card + .idea-card {
  margin-top: 14px;
}

@media (max-width: 900px) {
  .idea-form__grid {
    grid-template-columns: 1fr;
  }
}
</style>
