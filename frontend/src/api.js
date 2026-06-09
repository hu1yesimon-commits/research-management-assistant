const DEFAULT_BASE_URL = "http://127.0.0.1:8000";
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, "");

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null
        ? payload.detail || payload.message || JSON.stringify(payload)
        : String(payload);
    const error = new Error(detail || `Request failed with status ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}

export function getHealth() {
  return request("/health");
}

export function researchQuery(payload) {
  return request("/research/query", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function createExperimentLog(payload) {
  return request("/experiments/logs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function listExperimentLogs() {
  return request("/experiments/logs");
}

export function recommendIdeas(payload) {
  return request("/ideas/recommend", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function getCandidates() {
  return request("/papers/candidates");
}

export function acceptPaper(paperId, payload = null) {
  return request(`/papers/${paperId}/accept`, {
    method: "POST",
    headers: payload
      ? {
          "Content-Type": "application/json",
        }
      : undefined,
    body: payload ? JSON.stringify(payload) : undefined,
  });
}

export function uploadPdf(paperId, file) {
  const formData = new FormData();
  formData.append("file", file);
  return request(`/papers/${paperId}/upload_pdf`, {
    method: "POST",
    body: formData,
  });
}

export function embedPaper(paperId) {
  return request(`/papers/${paperId}/embed`, {
    method: "POST",
  });
}

export { API_BASE_URL };
