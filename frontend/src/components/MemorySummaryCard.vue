<template>
  <section class="panel panel--full">
    <div class="panel__heading">
      <div>
        <h2>Memory Summary</h2>
        <p>Review-gated memory counts and the latest structured experiment logs.</p>
      </div>
      <span class="badge badge--muted">summary</span>
    </div>

    <div v-if="error" class="alert alert--warning">
      <strong>Memory summary error:</strong> {{ error }}
    </div>

    <p v-if="loading" class="empty-state">Loading memory summary...</p>

    <template v-else-if="summary">
      <div class="panel__section">
        <div class="section-title">
          <h3>Counts</h3>
          <span class="meta">Current snapshot</span>
        </div>
        <div class="memory-summary-grid">
          <span>Pending review: {{ summary.pending_candidate_count ?? 0 }}</span>
          <span>Confirmed memory: {{ summary.confirmed_memory_count ?? 0 }}</span>
          <span>Known DOIs: {{ summary.known_doi_count ?? 0 }}</span>
          <span>Saved papers: {{ summary.saved_paper_count ?? summary.candidate_count ?? 0 }}</span>
        </div>
      </div>

      <div class="panel__section">
        <div class="section-title">
          <h3>Recent Logs</h3>
          <span class="meta">{{ summary.recent_logs?.length || 0 }} shown</span>
        </div>

        <ul v-if="summary.recent_logs?.length" class="stack-list">
          <li v-for="(log, index) in summary.recent_logs" :key="index" class="source-card">
            {{ log.content || "Log content unavailable." }}
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
