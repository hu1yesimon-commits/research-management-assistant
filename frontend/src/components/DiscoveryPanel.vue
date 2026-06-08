<template>
  <section class="panel">
    <div class="panel__heading">
      <div>
        <h2>Discovery</h2>
        <p>Recommended reading candidates. These are not the same as knowledge answer sources.</p>
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

        <p v-if="candidate.judgement?.reason" class="text-block">
          {{ candidate.judgement.reason }}
        </p>
      </li>
    </ul>

    <p v-else class="empty-state">No discovery candidates returned.</p>
  </section>
</template>

<script setup>
defineProps({
  discovery: {
    type: Object,
    required: true,
  },
});

function getCandidateKey(candidate) {
  return candidate.paper?.paper_id || candidate.paper?.title || JSON.stringify(candidate);
}

function formatAuthors(authors) {
  return Array.isArray(authors) && authors.length ? authors.join(", ") : "Authors unavailable";
}

function formatScore(value) {
  return typeof value === "number" ? value.toFixed(3) : "n/a";
}
</script>
