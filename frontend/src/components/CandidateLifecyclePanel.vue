<template>
  <div>
    <div class="lifecycle-toolbar">
      <button class="button button--ghost" type="button" @click="$emit('refresh')" :disabled="loading">
        Refresh
      </button>
    </div>

    <div v-if="error" class="alert alert--danger">
      <strong>Candidate load failed:</strong> {{ error }}
    </div>

    <p v-if="loading" class="empty-state">Loading candidates...</p>
    <p v-else-if="!candidates.length" class="empty-state">
      No saved papers yet. Accept a discovery candidate to start building your local research set.
    </p>

    <ul v-else class="stack-list">
      <li v-for="candidate in candidates" :key="candidate.paper_id" class="lifecycle-card">
        <div class="card-title-row">
          <h3>{{ candidate.title || "Untitled paper" }}</h3>
          <span class="status-pill">status: {{ candidate.status || "unknown" }}</span>
        </div>

        <div class="kv-grid">
          <span>paper_id: {{ candidate.paper_id }}</span>
          <span>DOI: {{ candidate.doi || "n/a" }}</span>
          <span>Venue: {{ candidate.venue || "n/a" }}</span>
          <span>Authors: {{ formatAuthors(candidate.authors) }}</span>
          <span>score: {{ formatSavedScore(candidate) }}</span>
        </div>

        <div class="lifecycle-actions">
          <button
            class="button"
            type="button"
            @click="$emit('accept', candidate.paper_id)"
            :disabled="isBusy(candidate.paper_id)"
          >
            Accept
          </button>

          <label class="file-picker">
            <span>{{ selectedFileName(candidate.paper_id) || "Choose PDF" }}</span>
            <input type="file" accept="application/pdf" @change="onFileChange(candidate.paper_id, $event)" />
          </label>

          <button
            class="button"
            type="button"
            @click="$emit('upload', candidate.paper_id)"
            :disabled="isBusy(candidate.paper_id)"
          >
            Upload PDF
          </button>

          <button
            class="button button--primary"
            type="button"
            @click="$emit('embed', candidate.paper_id)"
            :disabled="isBusy(candidate.paper_id)"
          >
            Embed / Advance Status
          </button>
        </div>

        <p class="hint">
          The same embed endpoint advances <code>uploaded -&gt; chunked</code> or <code>chunked -&gt; embedded</code>.
        </p>

        <p v-if="actionStates[candidate.paper_id]?.message" class="success-text">
          {{ actionStates[candidate.paper_id].message }}
        </p>
        <p v-if="actionStates[candidate.paper_id]?.error" class="error-text">
          {{ actionStates[candidate.paper_id].error }}
        </p>
      </li>
    </ul>
  </div>
</template>

<script setup>
const props = defineProps({
  candidates: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: "",
  },
  actionStates: {
    type: Object,
    default: () => ({}),
  },
  selectedFiles: {
    type: Object,
    default: () => ({}),
  },
});

const emit = defineEmits(["accept", "upload", "embed", "refresh", "select-file"]);

function formatAuthors(authors) {
  return Array.isArray(authors) && authors.length ? authors.join(", ") : "n/a";
}

function formatSavedScore(candidate) {
  const finalScore = candidate?.judgement?.scores?.final_score;
  return typeof finalScore === "number" ? finalScore.toFixed(3) : "score unavailable";
}

function isBusy(paperId) {
  return Boolean(props.actionStates[paperId]?.loading);
}

function selectedFileName(paperId) {
  return props.selectedFiles[paperId]?.name || "";
}

function onFileChange(paperId, event) {
  const [file] = event.target.files || [];
  if (file) {
    event.target.value = "";
  }
  emit("select-file", { paperId, file: file || null });
}
</script>
