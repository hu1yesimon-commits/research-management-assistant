<template>
  <main class="workbench-shell">
    <header class="topbar">
      <div>
        <h1>Research Workbench</h1>
        <p>Unified discovery and knowledge workflow for the current backend MVP.</p>
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

    <QueryForm :loading="queryLoading" @submit="handleQuery" />

    <section class="workspace-grid">
      <KnowledgePanel :knowledge="knowledgeSection" />
      <DiscoveryPanel
        :discovery="discoverySection"
        :action-states="candidateActionStates"
        @accept="handleDiscoveryAccept"
      />
    </section>

    <CandidateLifecyclePanel
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
  researchQuery,
  uploadPdf,
} from "../api";
import CandidateLifecyclePanel from "./CandidateLifecyclePanel.vue";
import DiscoveryPanel from "./DiscoveryPanel.vue";
import KnowledgePanel from "./KnowledgePanel.vue";
import QueryForm from "./QueryForm.vue";

const healthStatus = ref("checking");
const healthError = ref("");
const queryLoading = ref(false);
const queryError = ref("");
const queryResponse = ref(null);
const candidates = ref([]);
const candidatesLoading = ref(false);
const candidatesError = ref("");
const candidateActionStates = reactive({});
const selectedFiles = reactive({});

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

const discoverySection = computed(() => queryResponse.value?.discovery || defaultDiscoverySection);
const knowledgeSection = computed(() => queryResponse.value?.knowledge || defaultKnowledgeSection);

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
  } catch (error) {
    queryError.value = error.message;
  } finally {
    queryLoading.value = false;
  }
}

async function loadCandidates() {
  candidatesLoading.value = true;
  candidatesError.value = "";

  try {
    candidates.value = await getCandidates();
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
  } catch (error) {
    setCandidateState(paperId, { loading: false, error: error.message, message: "" });
  }
}

function setCandidateState(paperId, patch) {
  candidateActionStates[paperId] = {
    ...(candidateActionStates[paperId] || {}),
    ...patch,
  };
}
</script>
