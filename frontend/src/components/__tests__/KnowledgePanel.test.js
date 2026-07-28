import { describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";

import KnowledgePanel from "../KnowledgePanel.vue";

describe("KnowledgePanel", () => {
  test("shows not-run state when knowledge is disabled", () => {
    const wrapper = mount(KnowledgePanel, {
      props: {
        knowledge: {
          enabled: false,
          answer: null,
          sources: [],
          error: null,
          mode: null,
        },
      },
    });

    expect(wrapper.text()).toContain("Not run");
    expect(wrapper.text()).toContain("Ask about saved papers after embedding a PDF.");
  });

  test("shows no-match state when knowledge ran without sources", () => {
    const wrapper = mount(KnowledgePanel, {
      props: {
        knowledge: {
          enabled: true,
          answer: "No relevant knowledge chunks were found.",
          sources: [],
          error: null,
          mode: "deterministic",
        },
      },
    });

    expect(wrapper.text()).toContain("No relevant knowledge chunks were found.");
    expect(wrapper.text()).toContain("No matching embedded chunks returned.");
  });

  test("shows error without hiding sources content area", () => {
    const wrapper = mount(KnowledgePanel, {
      props: {
        knowledge: {
          enabled: true,
          answer: null,
          sources: [],
          error: "knowledge failed",
          mode: null,
        },
      },
    });

    expect(wrapper.text()).toContain("knowledge failed");
    expect(wrapper.text()).toContain("Knowledge Sources");
  });
});
