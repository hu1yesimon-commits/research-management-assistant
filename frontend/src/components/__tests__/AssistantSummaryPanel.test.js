import { describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";

import AssistantSummaryPanel from "../AssistantSummaryPanel.vue";

describe("AssistantSummaryPanel", () => {
  test("renders assistant route, message, next action, and notes", () => {
    const wrapper = mount(AssistantSummaryPanel, {
      props: {
        summary: {
          mode: "advanced",
          route: "advanced_search",
          coverage_score: 0.72,
          route_reason: "Existing knowledge overlaps with the query.",
          assistant_message: "Use local evidence and discovery together.",
          next_action: {
            type: "upload_pdf",
            message: "Review the recommended papers.",
            options: ["accept", "upload_pdf"],
          },
          suggested_user_actions: ["Review top papers", "Upload selected PDFs"],
          errors: [{ section: "memory", message: "memory unavailable" }],
        },
      },
    });

    const text = wrapper.text();
    expect(text).toContain("mode: advanced");
    expect(text).toContain("route: advanced_search");
    expect(text).toContain("72%");
    expect(text).toContain("Use local evidence and discovery together.");
    expect(text).toContain("Review the recommended papers.");
    expect(text).toContain("Review top papers");
    expect(text).toContain("Upload selected PDFs");
    expect(text).toContain("memory: memory unavailable");
  });

  test("stays hidden when no summary is available", () => {
    const wrapper = mount(AssistantSummaryPanel, {
      props: {
        summary: null,
      },
    });

    expect(wrapper.text()).not.toContain("Assistant Summary");
  });
});
