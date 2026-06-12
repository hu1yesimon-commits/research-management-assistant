import { describe, expect, test, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../../api", async () => {
  const actual = await vi.importActual("../../api");
  return {
    ...actual,
    getHealth: vi.fn().mockResolvedValue({ status: "ok" }),
    getCandidates: vi.fn().mockResolvedValue([]),
    researchAssistant: vi.fn(),
    researchQuery: vi.fn(),
    acceptPaper: vi.fn(),
    uploadPdf: vi.fn(),
    embedPaper: vi.fn(),
  };
});

import { researchAssistant, researchQuery } from "../../api";
import ResearchWorkbench from "../ResearchWorkbench.vue";

const assistantResponse = {
  discovery: {
    enabled: true,
    candidates: [
      {
        paper: {
          paper_id: "assistant-paper",
          title: "Assistant discovery paper",
          authors: ["Ada Lovelace"],
          doi: "10.0000/assistant",
          venue: "Assistant Venue",
        },
        judgement: {
          final_score: 0.91,
          llm_relevance_score: 0.88,
          reason: "Assistant discovery reason",
        },
      },
    ],
    error: null,
  },
  knowledge: {
    enabled: true,
    answer: "Assistant knowledge answer",
    sources: [
      {
        paper_id: "assistant-source",
        chunk_index: 1,
        distance: 0.12,
        title: "Assistant source title",
        text: "Assistant source evidence",
      },
    ],
    error: null,
    mode: "assistant-grounded",
  },
};

const queryResponse = {
  discovery: {
    enabled: true,
    candidates: [
      {
        paper: {
          paper_id: "query-paper",
          title: "Legacy query discovery paper",
          authors: ["Grace Hopper"],
          doi: "10.0000/query",
          venue: "Query Venue",
        },
        judgement: {
          final_score: 0.75,
          llm_relevance_score: 0.7,
          reason: "Legacy query discovery reason",
        },
      },
    ],
    error: null,
  },
  knowledge: {
    enabled: true,
    answer: "Legacy query knowledge answer",
    sources: [
      {
        paper_id: "query-source",
        chunk_index: 2,
        distance: 0.34,
        title: "Legacy query source title",
        text: "Legacy query source evidence",
      },
    ],
    error: null,
    mode: "query-grounded",
  },
};

describe("ResearchWorkbench result source switching", () => {
  test("shows assistant results after assistant success", async () => {
    researchAssistant.mockResolvedValueOnce(assistantResponse);
    const wrapper = mount(ResearchWorkbench);

    await wrapper.find("#assistant-query").setValue("assistant route");
    await wrapper.find("form.assistant-form").trigger("submit.prevent");
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain("Results source: assistant");
    expect(text).toContain("Assistant knowledge answer");
    expect(text).toContain("Assistant source evidence");
    expect(text).toContain("Assistant discovery paper");
    expect(text).toContain("Assistant discovery reason");
    expect(text).not.toContain("Legacy query knowledge answer");
    expect(text).not.toContain("Legacy query discovery paper");
  });

  test("switches back to research/query results after legacy query success", async () => {
    researchAssistant.mockResolvedValueOnce(assistantResponse);
    researchQuery.mockResolvedValueOnce(queryResponse);
    const wrapper = mount(ResearchWorkbench);

    await wrapper.find("#assistant-query").setValue("assistant route");
    await wrapper.find("form.assistant-form").trigger("submit.prevent");
    await flushPromises();

    await wrapper.find("#query").setValue("legacy route");
    await wrapper.find("form.query-form").trigger("submit.prevent");
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain("Results source: research/query");
    expect(text).toContain("Legacy query knowledge answer");
    expect(text).toContain("Legacy query source evidence");
    expect(text).toContain("Legacy query discovery paper");
    expect(text).toContain("Legacy query discovery reason");
    expect(text).not.toContain("Assistant knowledge answer");
    expect(text).not.toContain("Assistant discovery paper");
  });
});
