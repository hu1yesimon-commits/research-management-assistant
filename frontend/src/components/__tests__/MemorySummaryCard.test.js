import { describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";

import MemorySummaryCard from "../MemorySummaryCard.vue";

describe("MemorySummaryCard", () => {
  test("renders the lightweight memory summary contract", () => {
    const wrapper = mount(MemorySummaryCard, {
      props: {
        summary: {
          candidate_count: 0,
          saved_paper_count: 0,
          pending_candidate_count: 2,
          confirmed_memory_count: 5,
          known_doi_count: 3,
          recent_logs: [{ content: "latest log", tags: ["graph"] }],
        },
        loading: false,
        error: "",
      },
    });

    const text = wrapper.text();
    expect(text).toContain("Pending review");
    expect(text).toContain("2");
    expect(text).toContain("Confirmed memory");
    expect(text).toContain("5");
    expect(text).toContain("Known DOIs");
    expect(text).toContain("3");
    expect(text).toContain("latest log");
  });

  test("renders loading and endpoint errors", () => {
    const loadingWrapper = mount(MemorySummaryCard, {
      props: {
        summary: null,
        loading: true,
        error: "",
      },
    });
    expect(loadingWrapper.text()).toContain("Loading memory summary...");

    const errorWrapper = mount(MemorySummaryCard, {
      props: {
        summary: null,
        loading: false,
        error: "memory summary unavailable",
      },
    });
    expect(errorWrapper.text()).toContain("memory summary unavailable");
  });
});
