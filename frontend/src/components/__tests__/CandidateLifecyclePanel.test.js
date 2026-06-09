import { describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";

import CandidateLifecyclePanel from "../CandidateLifecyclePanel.vue";

describe("CandidateLifecyclePanel", () => {
  test("shows saved judgement score when available", () => {
    const wrapper = mount(CandidateLifecyclePanel, {
      props: {
        candidates: [
          {
            paper_id: "saved-1",
            title: "Saved Candidate",
            status: "accepted",
            authors: ["Tester"],
            judgement: {
              scores: {
                final_score: 0.85,
              },
            },
          },
        ],
      },
    });

    expect(wrapper.text()).toContain("score: 0.850");
  });

  test("shows score unavailable when no saved judgement score exists", () => {
    const wrapper = mount(CandidateLifecyclePanel, {
      props: {
        candidates: [
          {
            paper_id: "saved-2",
            title: "Saved Candidate Without Score",
            status: "accepted",
            authors: ["Tester"],
          },
        ],
      },
    });

    expect(wrapper.text()).toContain("score unavailable");
  });
});
