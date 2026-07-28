import { describe, expect, test, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

import ActiveCandidatesPanel from "../ActiveCandidatesPanel.vue";

function makeSessionCandidate(overrides = {}) {
  return {
    id: "candidate-1",
    batch_id: "batch-1",
    paper_key: "paper-1",
    status: "active",
    paper_snapshot: {
      paper_id: "paper-1",
      title: "Candidate paper title",
      authors: ["Ada Lovelace"],
      doi: "10.1000/paper-1",
      venue: "GraphConf",
    },
    judgement: {
      final_score: 0.91,
      llm_relevance_score: 0.88,
      reason: "Highly relevant.",
    },
    ...overrides,
  };
}

describe("ActiveCandidatesPanel", () => {
  test("only active candidates expose Accept", async () => {
    const accept = vi.fn().mockResolvedValue({ status: "accepted", paper_id: "paper-1" });
    const wrapper = mount(ActiveCandidatesPanel, {
      props: {
        candidates: [makeSessionCandidate({ id: "candidate-1", status: "active" })],
        acceptCandidate: accept,
      },
    });

    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(accept).toHaveBeenCalledWith("candidate-1");
    expect(wrapper.text()).toContain("Accepted");
  });

  test("removes a candidate when Accept reports expiration", async () => {
    const expired = Object.assign(new Error("Candidate expired"), { status: 409 });
    const wrapper = mount(ActiveCandidatesPanel, {
      props: {
        candidates: [makeSessionCandidate({ id: "candidate-1", status: "active" })],
        acceptCandidate: vi.fn().mockRejectedValue(expired),
      },
    });

    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Candidate expired; ask the Leader to search again.");
    expect(wrapper.text()).not.toContain("Candidate paper title");
  });
});
