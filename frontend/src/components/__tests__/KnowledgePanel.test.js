import { describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";

import KnowledgePanel from "../KnowledgePanel.vue";

describe("KnowledgePanel", () => {
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
