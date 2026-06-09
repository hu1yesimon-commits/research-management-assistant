import { afterEach, describe, expect, test, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("../../api", async () => {
  const actual = await vi.importActual("../../api");
  return {
    ...actual,
    getHealth: vi.fn().mockResolvedValue({ status: "ok" }),
    getCandidates: vi.fn().mockResolvedValue([]),
    researchQuery: vi.fn().mockResolvedValue({
      discovery: { enabled: true, candidates: [], error: null },
      knowledge: { enabled: true, answer: null, sources: [], error: null, mode: null },
    }),
    acceptPaper: vi.fn(),
    uploadPdf: vi.fn(),
    embedPaper: vi.fn(),
  };
});

import * as api from "../../api";
import ResearchWorkbench from "../ResearchWorkbench.vue";

describe("Idea Assistant frontend slice", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete global.fetch;
  });

  test("exposes idea assistant API helpers", async () => {
    const payload = {
      experiment_log: {
        task: "defect classification",
        model: "1D-CNN",
        dataset: "bearing fault dataset",
        metric_problem: "minority class PRAUC is low",
        tried_methods: ["class weighting", "focal loss"],
        observation: "recall improves but precision collapses",
        goal: "improve PRAUC without making model too heavy",
        tags: ["imbalanced-learning"],
      },
      save_log: true,
      include_discovery: false,
      top_k: 5,
      idea_count: 3,
    };

    const response = {
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: vi.fn().mockResolvedValue({ id: 12, created_at: "2026-06-09T10:20:30+00:00" }),
    };

    global.fetch = vi.fn().mockResolvedValue(response);

    expect(typeof api.createExperimentLog).toBe("function");
    expect(typeof api.listExperimentLogs).toBe("function");
    expect(typeof api.recommendIdeas).toBe("function");
    await api.createExperimentLog(payload.experiment_log);
    await api.listExperimentLogs();
    await api.recommendIdeas(payload);
    expect(global.fetch).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8000/experiments/logs",
      expect.objectContaining({
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload.experiment_log),
      }),
    );
    expect(global.fetch).toHaveBeenNthCalledWith(2, "http://127.0.0.1:8000/experiments/logs", {});
    expect(global.fetch).toHaveBeenNthCalledWith(
      3,
      "http://127.0.0.1:8000/ideas/recommend",
      expect.objectContaining({
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      }),
    );
  });

  test("mounts the workbench with an idea assistant panel slice", async () => {
    const wrapper = mount(ResearchWorkbench);

    await Promise.resolve();
    await Promise.resolve();

    expect(wrapper.find("#idea-assistant-panel").exists()).toBe(true);
    expect(wrapper.find("#save-log").exists()).toBe(true);
    expect(wrapper.find("#include-discovery").exists()).toBe(true);
    expect(wrapper.find("#idea-count").exists()).toBe(true);
  });
});
