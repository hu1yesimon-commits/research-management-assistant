<template>
  <main class="workbench-shell">
    <header class="topbar">
      <div>
        <h1>Research Workbench</h1>
        <p>Assistant-first research flow with direct query fallback and local lifecycle controls.</p>
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

    <AssistantWorkflowPanel
      :run-assistant="handleAssistant"
      @success="handleAssistantSuccess"
    />
    <AssistantSummaryPanel :summary="assistantSummary" />

    <p class="meta">Results source: {{ resultSourceLabel }}</p>
    <section class="workspace-grid">
      <KnowledgePanel :knowledge="knowledgeSection" />
      <DiscoveryPanel
        :discovery="discoverySection"
        :action-states="candidateActionStates"
        @accept="handleDiscoveryAccept"
      />
    </section>

    <section :class="['panel', 'panel--full', !isLifecycleOpen && 'panel--collapsed']">
      <div class="panel__heading">
        <div>
          <h2>Research Query</h2>
          <p>Fallback path for direct <code>POST /research/query</code> calls when you want manual control.</p>
        </div>
      </div>
      <QueryForm :loading="queryLoading" @submit="handleQuery" />
    </section>

    <section class="panel panel--full">
      <div class="panel__heading">
        <div>
          <h2>Saved Candidates & Lifecycle</h2>
          <p>Persisted papers, PDF upload, and embedding stay out of the main result flow by default.</p>
        </div>
        <button class="button button--ghost" type="button" @click="isLifecycleOpen = !isLifecycleOpen">
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

    <IdeaAssistantPanel />
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";

import {
  API_BASE_URL,
  acceptPaper,
  embedPaper,
  getCandidates,
  getHealth,
  getMemorySummary,
  researchAssistant,
  researchQuery,
  uploadPdf,
} from "../api";
import AssistantSummaryPanel from "./AssistantSummaryPanel.vue";
import AssistantWorkflowPanel from "./AssistantWorkflowPanel.vue";
import CandidateLifecyclePanel from "./CandidateLifecyclePanel.vue";
import DiscoveryPanel from "./DiscoveryPanel.vue";
import IdeaAssistantPanel from "./IdeaAssistantPanel.vue";
import KnowledgePanel from "./KnowledgePanel.vue";
import MemorySummaryCard from "./MemorySummaryCard.vue";
import QueryForm from "./QueryForm.vue";

const healthStatus = ref("checking");
const healthError = ref("");
const queryLoading = ref(false);
const queryError = ref("");
const queryResponse = ref(null);
const assistantResponse = ref(null);
const memorySummary = ref(null);
const memorySummaryLoading = ref(false);
const memorySummaryError = ref("");
const activeResultSource = ref("query");
const candidates = ref([]);
const candidatesLoading = ref(false);
const candidatesError = ref("");
const candidateActionStates = reactive({});
const selectedFiles = reactive({});
const isLifecycleOpen = ref(false);
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

const assistantSummary = computed(() => {
  if (!assistantResponse.value) {
    return null;
  }
  return {
    mode: assistantResponse.value.mode,
    route: assistantResponse.value.route,
    coverage_score: assistantResponse.value.coverage_score,
    route_reason: assistantResponse.value.route_reason,
    assistant_message: assistantResponse.value.assistant_message,
    next_action: assistantResponse.value.next_action,
    suggested_user_actions: assistantResponse.value.suggested_user_actions,
    errors: assistantResponse.value.errors,
  };
});

const activeResponse = computed(() => {
  if (activeResultSource.value === "assistant") {
    return assistantResponse.value;
  }
  return queryResponse.value;
});

const discoverySection = computed(() => activeResponse.value?.discovery || defaultDiscoverySection);
const knowledgeSection = computed(() => activeResponse.value?.knowledge || defaultKnowledgeSection);
const resultSourceLabel = computed(() => {
  return activeResultSource.value === "assistant" ? "assistant" : "research/query";
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

function handleAssistant(payload) {
  return researchAssistant(payload);
}

function handleAssistantSuccess(response) {
  assistantResponse.value = response;
  activeResultSource.value = "assistant";
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

async function loadCandidates() {
  candidatesLoading.value = true;
  candidatesError.value = "";

  try {
    const response = await getCandidates();
    candidates.value = Array.isArray(response) ? response : [];
  } catch (error) {
    candidatesError.value = error.message;
  } finally {
    candidatesLoading.value = false;
  }
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
