<template>
  <section class="panel panel--full">
    <div class="panel__heading">
      <div>
        <h2>Active Candidates</h2>
        <p>Only the current default session batch is actionable here.</p>
      </div>
      <span class="badge" :class="candidates.length ? 'badge--active' : 'badge--muted'">
        {{ candidates.length ? `${candidates.length} active` : "none active" }}
      </span>
    </div>

    <p v-if="notice" class="success-text">{{ notice }}</p>
    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
    <p v-if="!visibleCandidates.length" class="empty-state">
      No active candidates. Ask the Leader to search again when you need a fresh batch.
    </p>

    <ul v-else class="stack-list">
      <li
        v-for="candidate in visibleCandidates"
        :key="candidate.id"
        class="active-candidate-card"
      >
        <div class="card-title-row">
          <h3>{{ candidate.paper_snapshot?.title || "Untitled paper" }}</h3>
          <span class="status-pill">status: {{ candidate.status }}</span>
        </div>

        <div class="kv-grid">
          <span>paper_id: {{ candidate.paper_snapshot?.paper_id || "n/a" }}</span>
          <span>DOI: {{ candidate.paper_snapshot?.doi || "n/a" }}</span>
          <span>Venue: {{ candidate.paper_snapshot?.venue || "n/a" }}</span>
          <span>Authors: {{ formatAuthors(candidate.paper_snapshot?.authors) }}</span>
          <span>score: {{ formatScore(candidate.judgement?.final_score) }}</span>
          <span>LLM relevance: {{ formatScore(candidate.judgement?.llm_relevance_score) }}</span>
        </div>

        <p v-if="candidate.judgement?.reason" class="hint">{{ candidate.judgement.reason }}</p>

        <div class="lifecycle-actions">
          <button class="button button--primary" type="button" @click="accept(candidate.id)" :disabled="busyId === candidate.id">
            {{ busyId === candidate.id ? "Accepting..." : "Accept" }}
          </button>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  candidates: {
    type: Array,
    default: () => [],
  },
  acceptCandidate: {
    type: Function,
    required: true,
  },
});

const emit = defineEmits(["accepted", "expired"]);

const hiddenCandidateIds = ref(new Set());
const busyId = ref("");
const notice = ref("");
const errorMessage = ref("");

const visibleCandidates = computed(() =>
  props.candidates.filter((candidate) => !hiddenCandidateIds.value.has(candidate.id)),
);

function formatAuthors(authors) {
  return Array.isArray(authors) && authors.length ? authors.join(", ") : "n/a";
}

function formatScore(score) {
  return typeof score === "number" ? score.toFixed(3) : "n/a";
}

async function accept(candidateId) {
  busyId.value = candidateId;
  notice.value = "";
  errorMessage.value = "";

  try {
    await props.acceptCandidate(candidateId);
    hiddenCandidateIds.value = new Set([...hiddenCandidateIds.value, candidateId]);
    notice.value = "Accepted";
    emit("accepted", candidateId);
  } catch (error) {
    if (error?.status === 409) {
      hiddenCandidateIds.value = new Set([...hiddenCandidateIds.value, candidateId]);
      errorMessage.value = "Candidate expired; ask the Leader to search again.";
      emit("expired", candidateId);
    } else {
      errorMessage.value = error?.message || "Active candidate accept failed";
    }
  } finally {
    busyId.value = "";
  }
}
</script>
