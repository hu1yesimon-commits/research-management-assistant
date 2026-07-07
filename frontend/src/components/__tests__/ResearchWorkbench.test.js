import { beforeEach, describe, expect, test, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../../api", async () => {
  const actual = await vi.importActual("../../api");
  return {
    ...actual,
    getHealth: vi.fn().mockResolvedValue({ status: "ok" }),
    getSessionMessages: vi.fn().mockResolvedValue({
      items: [
        { id: 1, role: "user", content: { text: "Earlier question" } },
        { id: 2, role: "assistant", content: { assistant_message: "Earlier answer" } },
      ],
      next_before_id: null,
    }),
    createSessionTurn: vi.fn(),
    getActiveCandidates: vi.fn().mockResolvedValue([]),
    getSavedPapers: vi.fn().mockResolvedValue([]),
    getMemorySummary: vi.fn().mockResolvedValue({
      candidate_count: 0,
      saved_paper_count: 0,
      pending_candidate_count: 2,
      confirmed_memory_count: 5,
      known_doi_count: 3,
      recent_logs: [{ content: "latest log", tags: ["graph"] }],
    }),
    researchQuery: vi.fn(),
    acceptPaper: vi.fn(),
    uploadPdf: vi.fn(),
    embedPaper: vi.fn(),
  };
});

import { createSessionTurn, getActiveCandidates, getSavedPapers, getSessionMessages, researchQuery } from "../../api";
import ResearchWorkbench from "../ResearchWorkbench.vue";

const sessionTurnResponse = {
  session_id: "default",
  turn_id: "turn-2",
  status: "completed",
  assistant_message: "I can search with local context and discovery together.",
  active_candidates: [],
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
  agent_runs: [],
  errors: [],
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
  beforeEach(() => {
    vi.clearAllMocks();
    getSessionMessages.mockResolvedValue({
      items: [
        { id: 1, role: "user", content: { text: "Earlier question" } },
        { id: 2, role: "assistant", content: { assistant_message: "Earlier answer" } },
      ],
      next_before_id: null,
    });
    getActiveCandidates.mockResolvedValue([]);
    getSavedPapers.mockResolvedValue([]);
  });

  test("renders the session-first layout and loads default session resources on mount", async () => {
    const wrapper = mount(ResearchWorkbench);
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain("Session Chat");
    expect(text).toContain("Earlier answer");
    expect(text).toContain("Memory Summary");
    expect(text).toContain("Pending review: 2");
    expect(text).toContain("Confirmed memory: 5");
    expect(text).toContain("Legacy tools");
    expect(text).toContain("Saved Candidates & Lifecycle");
    expect(getSessionMessages).toHaveBeenCalledWith("default");
    expect(getActiveCandidates).toHaveBeenCalledWith("default");
    expect(getSavedPapers).toHaveBeenCalled();
  });

  test("submits a session turn, reloads messages and active candidates, and updates the latest result", async () => {
    createSessionTurn.mockResolvedValueOnce(sessionTurnResponse);
    getSessionMessages.mockResolvedValueOnce({
      items: [
        { id: 1, role: "user", content: { text: "Earlier question" } },
        { id: 2, role: "assistant", content: { assistant_message: "Earlier answer" } },
      ],
      next_before_id: null,
    });
    getSessionMessages.mockResolvedValueOnce({
      items: [
        { id: 1, role: "user", content: { text: "Earlier question" } },
        { id: 2, role: "assistant", content: { assistant_message: "Earlier answer" } },
        { id: 3, role: "user", content: { text: "Find fresh papers" } },
        { id: 4, role: "assistant", content: { assistant_message: "I can search with local context and discovery together." } },
      ],
      next_before_id: null,
    });
    const wrapper = mount(ResearchWorkbench);
    await flushPromises();

    await wrapper.find("#session-chat-input").setValue("Find fresh papers");
    await wrapper.find("form.session-chat-form").trigger("submit.prevent");
    await flushPromises();

    const text = wrapper.text();
    expect(createSessionTurn).toHaveBeenCalledWith(
      "default",
      expect.objectContaining({
        message: "Find fresh papers",
        idempotency_key: expect.any(String),
      }),
    );
    expect(getSessionMessages).toHaveBeenCalledTimes(2);
    expect(getActiveCandidates).toHaveBeenCalledTimes(2);
    expect(text).toContain("Assistant knowledge answer");
    expect(text).toContain("I can search with local context and discovery together.");
  });

  test("keeps legacy query tools behind a collapsed panel and can still run them", async () => {
    researchQuery.mockRejectedValueOnce(new Error("query fallback failed"));
    const wrapper = mount(ResearchWorkbench);
    await flushPromises();

    expect(wrapper.text()).not.toContain("Direct Research Query");

    await wrapper.find("button.legacy-tools__toggle").trigger("click");
    expect(wrapper.text()).toContain("Direct Research Query");

    await wrapper.find("#query").setValue("legacy route");
    await wrapper.find("form.query-form").trigger("submit.prevent");
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain("query fallback failed");
  });

  test("keeps lifecycle collapsed until the user opens it", async () => {
    getSavedPapers.mockResolvedValueOnce([
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

    await wrapper.find("button.lifecycle-tools__toggle").trigger("click");
    expect(wrapper.text()).toContain("Upload PDF");
  });

  test("clears stale assistant results after a later assistant failure", async () => {
    createSessionTurn.mockResolvedValueOnce(sessionTurnResponse).mockRejectedValueOnce(new Error("assistant offline"));
    getSessionMessages
      .mockResolvedValueOnce({
        items: [
          { id: 1, role: "user", content: { text: "Earlier question" } },
          { id: 2, role: "assistant", content: { assistant_message: "Earlier answer" } },
        ],
        next_before_id: null,
      })
      .mockResolvedValueOnce({
        items: [
          { id: 1, role: "user", content: { text: "Earlier question" } },
          { id: 2, role: "assistant", content: { assistant_message: "Earlier answer" } },
          { id: 3, role: "user", content: { text: "assistant route" } },
          { id: 4, role: "assistant", content: { assistant_message: "I can search with local context and discovery together." } },
        ],
        next_before_id: null,
      });
    const wrapper = mount(ResearchWorkbench);
    await flushPromises();

    await wrapper.find("#session-chat-input").setValue("assistant route");
    await wrapper.find("form.session-chat-form").trigger("submit.prevent");
    await flushPromises();

    expect(wrapper.text()).toContain("Assistant knowledge answer");

    await wrapper.find("#session-chat-input").setValue("assistant route retry");
    await wrapper.find("form.session-chat-form").trigger("submit.prevent");
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain("assistant offline");
    expect(text).not.toContain("Assistant knowledge answer");
  });
});
