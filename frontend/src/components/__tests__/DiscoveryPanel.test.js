import { describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";

import DiscoveryPanel from "../DiscoveryPanel.vue";

describe("DiscoveryPanel", () => {
  test("renders candidates even when optional fields are missing", () => {
    const wrapper = mount(DiscoveryPanel, {
      props: {
        discovery: {
          enabled: true,
          candidates: [
            {
              paper: {
                paper_id: "candidate-1",
                title: "Sparse Candidate",
              },
              judgement: {},
            },
          ],
          error: null,
        },
      },
    });

    expect(wrapper.text()).toContain("Sparse Candidate");
    expect(wrapper.text()).toContain("candidate-1");
  });

  test("emits accept with the current candidate payload", async () => {
    const candidate = {
      paper: {
        paper_id: "candidate-2",
        title: "Actionable Candidate",
      },
      judgement: {
        decision: "accept",
      },
    };

    const wrapper = mount(DiscoveryPanel, {
      props: {
        discovery: {
          enabled: true,
          candidates: [candidate],
          error: null,
        },
      },
    });

    await wrapper.get('button[type="button"]').trigger("click");

    expect(wrapper.emitted("accept")).toEqual([[candidate]]);
  });

  test("shows candidate count, mock scoring badge, and placeholder scoring copy", () => {
    const wrapper = mount(DiscoveryPanel, {
      props: {
        discovery: {
          enabled: true,
          candidates: [
            {
              paper: {
                paper_id: "candidate-3",
                title: "Mock Candidate",
              },
              judgement: {
                final_score: 0.5,
                llm_relevance_score: 0.5,
                tags: ["mock"],
              },
            },
            {
              paper: {
                paper_id: "candidate-4",
                title: "Mock Candidate 2",
              },
              judgement: {
                final_score: 0.5,
                llm_relevance_score: 0.5,
                tags: ["mock"],
              },
            },
          ],
          error: null,
        },
      },
    });

    expect(wrapper.text()).toContain("Showing 2 discovery candidates");
    expect(wrapper.text()).toContain("mock scoring");
    expect(wrapper.text()).toContain("Current judge output may be a placeholder");
    expect(wrapper.text()).toContain("Scores are tied across all returned candidates");
  });

  test("does not show placeholder scoring copy for non-mock varied scores", () => {
    const wrapper = mount(DiscoveryPanel, {
      props: {
        discovery: {
          enabled: true,
          candidates: [
            {
              paper: {
                paper_id: "candidate-5",
                title: "LLM Judged Candidate",
              },
              judgement: {
                final_score: 0.82,
                llm_relevance_score: 0.9,
                tags: ["deepseek"],
              },
            },
            {
              paper: {
                paper_id: "candidate-6",
                title: "Another LLM Judged Candidate",
              },
              judgement: {
                final_score: 0.64,
                llm_relevance_score: 0.7,
                tags: ["deepseek"],
              },
            },
          ],
          error: null,
        },
      },
    });

    expect(wrapper.text()).toContain("LLM Judged Candidate");
    expect(wrapper.text()).not.toContain("Current judge output may be a placeholder");
    expect(wrapper.text()).not.toContain("mock scoring");
    expect(wrapper.text()).not.toContain("Scores are tied across all returned candidates");
  });
});
