<template>
  <section class="panel">
    <div class="panel__heading">
      <div>
        <h2>Discovery</h2>
        <p>Current query results only. These are not stored in SQLite until you click Accept.</p>
      </div>
      <span class="badge" :class="discovery.enabled ? 'badge--active' : 'badge--muted'">
        {{ discovery.enabled ? "Enabled" : "Disabled" }}
      </span>
    </div>

    <div v-if="discovery.error" class="alert alert--warning">
      <strong>Discovery error:</strong> {{ discovery.error }}
    </div>

    <ul v-if="discovery.candidates?.length" class="stack-list">
      <li
        v-for="candidate in discovery.candidates"
        :key="getCandidateKey(candidate)"
        class="candidate-card"
      >
        <div class="card-title-row">
          <h3>{{ candidate.paper?.title || "Untitled candidate" }}</h3>
          <span class="meta">{{ candidate.paper?.paper_id || "no paper_id" }}</span>
        </div>

        <p class="authors-line">{{ formatAuthors(candidate.paper?.authors) }}</p>

        <div class="kv-grid">
          <span>DOI: {{ candidate.paper?.doi || "n/a" }}</span>
          <span>Venue: {{ candidate.paper?.venue || "n/a" }}</span>
          <span>final_score: {{ formatScore(candidate.judgement?.final_score) }}</span>
          <span>relevance: {{ formatScore(candidate.judgement?.llm_relevance_score) }}</span>
        </div>

        <div class="lifecycle-actions">
          <button
            class="button button--primary"
            type="button"
            @click="emit('accept', candidate)"
            :disabled="isBusy(candidate.paper?.paper_id)"
          >
            Accept
          </button>
        </div>

        <p v-if="candidate.judgement?.reason" class="text-block">
          {{ candidate.judgement.reason }}
        </p>

        <p v-if="candidate.paper?.paper_id && actionStates[candidate.paper.paper_id]?.message" class="success-text">
          {{ actionStates[candidate.paper.paper_id].message }}
        </p>
        <p v-if="candidate.paper?.paper_id && actionStates[candidate.paper.paper_id]?.error" class="error-text">
          {{ actionStates[candidate.paper.paper_id].error }}
        </p>
      </li>
    </ul>

    <p v-else class="empty-state">No discovery candidates returned.</p>
  </section>
</template>

<script setup>
const props = defineProps({
  discovery: {
    type: Object,
    required: true,
  },
  actionStates: {
    type: Object,
    default: () => ({}),
  },
});

const emit = defineEmits(["accept"]);

function getCandidateKey(candidate) {
  return candidate.paper?.paper_id || candidate.paper?.title || JSON.stringify(candidate);
}

function formatAuthors(authors) {
  return Array.isArray(authors) && authors.length ? authors.join(", ") : "Authors unavailable";
}

function formatScore(value) {
  return typeof value === "number" ? value.toFixed(3) : "n/a";
}

function isBusy(paperId) {
  return Boolean(paperId && props.actionStates[paperId]?.loading);
}
</script>
