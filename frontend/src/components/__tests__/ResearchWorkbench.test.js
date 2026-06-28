import { describe, expect, test, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../../api", async () => {
  const actual = await vi.importActual("../../api");
  return {
    ...actual,
    getHealth: vi.fn().mockResolvedValue({ status: "ok" }),
    getCandidates: vi.fn().mockResolvedValue([]),
    getMemorySummary: vi.fn().mockResolvedValue({
      candidate_count: 0,
      saved_paper_count: 0,
      pending_candidate_count: 2,
      confirmed_memory_count: 5,
      known_doi_count: 3,
      recent_logs: [{ content: "latest log", tags: ["graph"] }],
    }),
    researchAssistant: vi.fn(),
    researchQuery: vi.fn(),
    acceptPaper: vi.fn(),
    uploadPdf: vi.fn(),
    embedPaper: vi.fn(),
  };
});

import { getCandidates, researchAssistant, researchQuery } from "../../api";
import ResearchWorkbench from "../ResearchWorkbench.vue";

const assistantResponse = {
  mode: "advanced",
  route: "advanced_search",
  coverage_score: 0.72,
  route_reason: "Existing knowledge has enough overlap with the query.",
  assistant_message: "I can search with local context and discovery together.",
  next_action: {
    type: "upload_pdf",
    message: "Review the recommended papers.",
    options: ["accept", "upload_pdf"],
  },
  suggested_user_actions: ["Review top papers", "Upload selected PDFs"],
  errors: [{ section: "memory", message: "memory unavailable" }],
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
  ideas: [],
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

describe("ResearchWorkbench", () => {
  test("renders the assistant-first layout with memory summary and collapsed lifecycle", async () => {
    const wrapper = mount(ResearchWorkbench);
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain("Assistant Workflow");
    expect(text).toContain("Memory Summary");
    expect(text).toContain("Pending review: 2");
    expect(text).toContain("Confirmed memory: 5");
    expect(text).toContain("Research Query");
    expect(text).toContain("Saved Candidates & Lifecycle");
    expect(text).not.toContain("No saved candidates in SQLite yet.");
  });

  test("shows assistant summary and switches visible results to assistant output", async () => {
    researchAssistant.mockResolvedValueOnce(assistantResponse);
    const wrapper = mount(ResearchWorkbench);

    await wrapper.find("#assistant-query").setValue("assistant route");
    await wrapper.find("form.assistant-form").trigger("submit.prevent");
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain("Assistant Summary");
    expect(text).toContain("route: advanced_search");
    expect(text).toContain("72%");
    expect(text).toContain("Assistant knowledge answer");
    expect(text).toContain("Assistant discovery paper");
    expect(text).toContain("Results source: assistant");
  });

  test("preserves assistant results if the fallback query fails", async () => {
    researchAssistant.mockResolvedValueOnce(assistantResponse);
    researchQuery.mockRejectedValueOnce(new Error("query fallback failed"));
    const wrapper = mount(ResearchWorkbench);

    await wrapper.find("#assistant-query").setValue("assistant route");
    await wrapper.find("form.assistant-form").trigger("submit.prevent");
    await flushPromises();

    await wrapper.find("#query").setValue("legacy route");
    await wrapper.find("form.query-form").trigger("submit.prevent");
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain("query fallback failed");
    expect(text).toContain("Assistant knowledge answer");
    expect(text).toContain("Assistant discovery paper");
    expect(text).toContain("Results source: assistant");
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
    expect(text).toContain("Legacy query discovery paper");
  });

  test("keeps lifecycle collapsed until the user opens it", async () => {
    getCandidates.mockResolvedValueOnce([
      {
        paper_id: "saved-paper-1",
        title: "Saved paper",
        doi: "10.0000/saved",
        venue: "Saved Venue",
        authors: ["Ada Lovelace"],
        judgement: {
          scores: {
            final_score: 0.91,
          },
        },
      },
    ]);
    const wrapper = mount(ResearchWorkbench);
    await flushPromises();

    expect(wrapper.text()).toContain("Saved Candidates & Lifecycle");
    expect(wrapper.text()).not.toContain("Upload PDF");

    await wrapper.find("button.button--ghost").trigger("click");
    expect(wrapper.text()).toContain("Upload PDF");
  });
});
