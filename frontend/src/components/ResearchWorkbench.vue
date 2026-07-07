<template>
  <main class="workbench-shell">
    <header class="topbar">
      <div>
        <h1>Research Workbench</h1>
        <p>Persistent default-session chat with legacy query and lifecycle tools kept available during migration.</p>
      </div>
      <div class="status-cluster">
        <span class="badge" :class="healthBadgeClass">{{ healthLabel }}</span>
        <span class="meta">API base: {{ apiBaseUrl }}</span>
      </div>
    </header>

    <div v-if="healthError" class="alert alert--danger">
      <strong>Backend health check failed:</strong> {{ healthError }}
    </div>

    <div v-if="queryError" class="alert alert--danger">
      <strong>Search failed:</strong> {{ queryError }}
    </div>

    <div v-if="hasPartialFailure" class="alert alert--warning">
      <strong>Partial failure:</strong> one workflow section failed, but the other section may still be usable.
    </div>

    <SessionChatPanel
      :messages="sessionMessages"
      :run-turn="handleSessionTurn"
      @turn-completed="handleSessionTurnCompleted"
      @turn-failed="handleSessionTurnFailed"
    />
    <section class="workspace-grid">
      <ActiveCandidatesPanel
        :candidates="activeCandidates"
        :accept-candidate="handleActiveCandidateAccept"
      />
      <AgentTracePanel
        :plan="latestTurnResponse?.plan || null"
        :agent-runs="latestTurnResponse?.agent_runs || []"
        :errors="latestTurnResponse?.errors || []"
      />
    </section>
    <section class="workspace-grid">
      <KnowledgePanel :knowledge="knowledgeSection" />
      <DiscoveryPanel
        :discovery="discoverySection"
        :action-states="candidateActionStates"
        @accept="handleDiscoveryAccept"
      />
    </section>

    <section :class="['panel', 'panel--full', !isLegacyToolsOpen && 'panel--collapsed']">
      <div class="panel__heading">
        <div>
          <h2>Legacy tools</h2>
          <p>Temporary compatibility path for direct query control and the standalone idea form.</p>
        </div>
        <button class="button button--ghost legacy-tools__toggle" type="button" @click="isLegacyToolsOpen = !isLegacyToolsOpen">
          {{ isLegacyToolsOpen ? "Hide" : "Open" }}
        </button>
      </div>

      <div v-if="isLegacyToolsOpen" class="legacy-tools__body">
        <section class="panel__section">
          <div class="section-title">
            <div>
              <h3>Research Query</h3>
              <p>Fallback path for direct <code>POST /research/query</code> calls when you want manual control.</p>
            </div>
          </div>
          <QueryForm :loading="queryLoading" @submit="handleQuery" />
        </section>

        <section class="panel__section">
          <IdeaAssistantPanel />
        </section>
      </div>
    </section>

    <section class="panel panel--full">
      <div class="panel__heading">
        <div>
          <h2>Saved Candidates & Lifecycle</h2>
          <p>Persisted papers, PDF upload, and embedding stay out of the main result flow by default.</p>
        </div>
        <button class="button button--ghost lifecycle-tools__toggle" type="button" @click="isLifecycleOpen = !isLifecycleOpen">
          {{ isLifecycleOpen ? "Hide" : "Open" }}
        </button>
      </div>

      <p v-if="candidateActionHint" class="success-text">{{ candidateActionHint }}</p>

      <p v-if="!isLifecycleOpen && !candidates.length" class="empty-state">
        No saved papers yet. Accept a discovery candidate to start building your local research set.
      </p>

      <CandidateLifecyclePanel
        v-if="isLifecycleOpen"
        :candidates="candidates"
        :loading="candidatesLoading"
        :error="candidatesError"
        :action-states="candidateActionStates"
        :selected-files="selectedFiles"
        @accept="handleAccept"
        @upload="handleUpload"
        @embed="handleEmbed"
        @refresh="loadCandidates"
        @select-file="handleFileSelection"
      />
    </section>

    <MemorySummaryCard
      :summary="memorySummary"
      :loading="memorySummaryLoading"
      :error="memorySummaryError"
    />
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";

import {
  API_BASE_URL,
  acceptPaper,
  acceptSessionCandidate,
  createSessionTurn,
  embedPaper,
  getActiveCandidates,
  getHealth,
  getMemorySummary,
  getSavedPapers,
  getSessionMessages,
  researchQuery,
  uploadPdf,
} from "../api";
import ActiveCandidatesPanel from "./ActiveCandidatesPanel.vue";
import AgentTracePanel from "./AgentTracePanel.vue";
import CandidateLifecyclePanel from "./CandidateLifecyclePanel.vue";
import DiscoveryPanel from "./DiscoveryPanel.vue";
import KnowledgePanel from "./KnowledgePanel.vue";
import MemorySummaryCard from "./MemorySummaryCard.vue";
import QueryForm from "./QueryForm.vue";
import SessionChatPanel from "./SessionChatPanel.vue";
import IdeaAssistantPanel from "./IdeaAssistantPanel.vue";

const healthStatus = ref("checking");
const healthError = ref("");
const queryLoading = ref(false);
const queryError = ref("");
const queryResponse = ref(null);
const latestTurnResponse = ref(null);
const memorySummary = ref(null);
const memorySummaryLoading = ref(false);
const memorySummaryError = ref("");
const activeResultSource = ref("session");
const sessionId = "default";
const sessionMessages = ref([]);
const activeCandidates = ref([]);
const candidates = ref([]);
const candidatesLoading = ref(false);
const candidatesError = ref("");
const candidateActionStates = reactive({});
const selectedFiles = reactive({});
const isLifecycleOpen = ref(false);
const isLegacyToolsOpen = ref(false);
const candidateActionHint = ref("");

const apiBaseUrl = API_BASE_URL;

const defaultDiscoverySection = {
  enabled: true,
  candidates: [],
  error: null,
};

const defaultKnowledgeSection = {
  enabled: true,
  answer: null,
  sources: [],
  error: null,
  mode: null,
};

const discoverySection = computed(() =>
  activeResultSource.value === "query"
    ? queryResponse.value?.discovery || defaultDiscoverySection
    : defaultDiscoverySection,
);

const knowledgeSection = computed(() => {
  if (activeResultSource.value === "session") {
    return latestTurnResponse.value?.knowledge || defaultKnowledgeSection;
  }
  return queryResponse.value?.knowledge || defaultKnowledgeSection;
});

const hasPartialFailure = computed(() => {
  return Boolean(discoverySection.value.error || knowledgeSection.value.error);
});

const healthLabel = computed(() => {
  if (healthStatus.value === "ok") {
    return "Backend: ok";
  }
  if (healthStatus.value === "error") {
    return "Backend: unreachable";
  }
  return "Backend: checking";
});

const healthBadgeClass = computed(() => {
  if (healthStatus.value === "ok") {
    return "badge--active";
  }
  if (healthStatus.value === "error") {
    return "badge--danger";
  }
  return "badge--muted";
});

onMounted(() => {
  loadHealth();
  loadSessionMessages();
  loadActiveCandidates();
  loadCandidates();
  loadMemorySummary();
});

async function loadHealth() {
  healthError.value = "";
  healthStatus.value = "checking";

  try {
    const response = await getHealth();
    healthStatus.value = response.status === "ok" ? "ok" : "error";
    if (response.status !== "ok") {
      healthError.value = `Unexpected health payload: ${JSON.stringify(response)}`;
    }
  } catch (error) {
    healthStatus.value = "error";
    healthError.value = error.message;
  }
}

async function handleQuery(payload) {
  queryLoading.value = true;
  queryError.value = "";

  try {
    queryResponse.value = await researchQuery(payload);
    activeResultSource.value = "query";
  } catch (error) {
    queryError.value = error.message;
  } finally {
    queryLoading.value = false;
  }
}

function handleSessionTurn(payload) {
  candidates.value = [];
  activeCandidates.value = [];
  return createSessionTurn(sessionId, payload);
}

async function handleSessionTurnCompleted(response) {
  latestTurnResponse.value = response;
  activeResultSource.value = "session";
  await Promise.all([loadSessionMessages(), loadActiveCandidates()]);
}

async function loadMemorySummary() {
  memorySummaryLoading.value = true;
  memorySummaryError.value = "";

  try {
    memorySummary.value = await getMemorySummary();
  } catch (error) {
    memorySummaryError.value = error.message;
  } finally {
    memorySummaryLoading.value = false;
  }
}

function handleSessionTurnFailed() {
  latestTurnResponse.value = null;
  activeResultSource.value = queryResponse.value ? "query" : "session";
}

async function loadCandidates() {
  candidatesLoading.value = true;
  candidatesError.value = "";

  try {
    const response = await getSavedPapers();
    candidates.value = Array.isArray(response) ? response : [];
  } catch (error) {
    candidatesError.value = error.message;
  } finally {
    candidatesLoading.value = false;
  }
}

async function loadSessionMessages() {
  try {
    const response = await getSessionMessages(sessionId);
    sessionMessages.value = Array.isArray(response?.items) ? response.items : [];
  } catch {
    sessionMessages.value = [];
  }
}

async function loadActiveCandidates() {
  try {
    const response = await getActiveCandidates(sessionId);
    activeCandidates.value = Array.isArray(response) ? response : [];
  } catch {
    activeCandidates.value = [];
  }
}

async function handleActiveCandidateAccept(candidateId) {
  await acceptSessionCandidate(sessionId, candidateId);
  activeCandidates.value = activeCandidates.value.filter(
    (candidate) => candidate.id !== candidateId,
  );
  await Promise.all([loadCandidates(), loadMemorySummary()]);
}

function handleFileSelection({ paperId, file }) {
  if (file) {
    selectedFiles[paperId] = file;
  } else {
    delete selectedFiles[paperId];
  }
}

async function handleAccept(paperId) {
  await runCandidateAction(paperId, async () => {
    const result = await acceptPaper(paperId);
    candidateActionHint.value = "";
    return `Accepted: ${result.status}`;
  });
}

async function handleDiscoveryAccept(candidate) {
  const paperId = candidate?.paper?.paper_id;
  if (!paperId || !candidate?.paper) {
    return;
  }

  await runCandidateAction(paperId, async () => {
    const result = await acceptPaper(paperId, {
      paper: candidate.paper,
      judgement: candidate.judgement || null,
    });
    candidateActionHint.value = "Paper saved. Open Saved Candidates to upload the PDF and continue embedding.";
    return `Saved and accepted: ${result.status}`;
  });
}

async function handleUpload(paperId) {
  const file = selectedFiles[paperId];
  if (!file) {
    setCandidateState(paperId, { error: "Select a PDF file before uploading." });
    return;
  }

  await runCandidateAction(paperId, async () => {
    const result = await uploadPdf(paperId, file);
    return `Uploaded: ${result.status}`;
  });
}

async function handleEmbed(paperId) {
  await runCandidateAction(paperId, async () => {
    const result = await embedPaper(paperId);
    return `Advanced to: ${result.status}`;
  });
}

async function runCandidateAction(paperId, action) {
  setCandidateState(paperId, { loading: true, error: "", message: "" });

  try {
    const message = await action();
    setCandidateState(paperId, { loading: false, error: "", message });
    await loadCandidates();
    await loadMemorySummary();
  } catch (error) {
    setCandidateState(paperId, {
      loading: false,
      error: error.message || "Candidate action failed",
      message: "",
    });
  }
}

function setCandidateState(paperId, patch) {
  candidateActionStates[paperId] = {
    loading: false,
    error: "",
    message: "",
    ...candidateActionStates[paperId],
    ...patch,
  };
}
</script>
