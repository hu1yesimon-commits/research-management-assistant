<template>
  <section class="panel">
    <div class="panel__heading">
      <div>
        <h2>Knowledge</h2>
        <p>Grounded answer and evidence from already embedded local knowledge chunks.</p>
      </div>
      <span class="badge" :class="knowledge.enabled ? 'badge--active' : 'badge--muted'">
        {{ knowledge.enabled ? "Enabled" : "Disabled" }}
      </span>
    </div>

    <div v-if="knowledge.error" class="alert alert--warning">
      <strong>Knowledge error:</strong> {{ knowledge.error }}
    </div>

    <div class="panel__section">
      <div class="section-title">
        <h3>Answer</h3>
        <span v-if="knowledge.mode" class="meta">mode: {{ knowledge.mode }}</span>
      </div>
      <p v-if="knowledge.answer" class="answer-block">{{ knowledge.answer }}</p>
      <p v-else class="empty-state">No knowledge answer yet.</p>
    </div>

    <div class="panel__section">
      <div class="section-title">
        <h3>Knowledge Sources</h3>
        <span class="meta">Embedded knowledge base evidence only</span>
      </div>

      <ul v-if="knowledge.sources?.length" class="stack-list">
        <li v-for="source in knowledge.sources" :key="source.paper_id + '-' + source.chunk_index" class="source-card">
          <div class="card-title-row">
            <h4>{{ source.title || "Untitled source" }}</h4>
            <span class="meta">paper_id: {{ source.paper_id }}</span>
          </div>
          <div class="kv-grid">
            <span>chunk_index: {{ source.chunk_index }}</span>
            <span>distance: {{ formatDistance(source.distance) }}</span>
          </div>
          <p class="text-block">{{ source.text || "No source text returned." }}</p>
        </li>
      </ul>

      <p v-else class="empty-state">No knowledge sources returned.</p>
    </div>
  </section>
</template>

<script setup>
defineProps({
  knowledge: {
    type: Object,
    required: true,
  },
});

function formatDistance(value) {
  return typeof value === "number" ? value.toFixed(4) : "n/a";
}
</script>
