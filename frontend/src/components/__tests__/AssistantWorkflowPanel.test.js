import { describe, expect, test, vi } from "vitest";
import { mount } from "@vue/test-utils";

import AssistantWorkflowPanel from "../AssistantWorkflowPanel.vue";

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
  discovery: { enabled: true, candidates: [], error: null },
  knowledge: { enabled: true, answer: "Grounded answer", sources: [], error: null, mode: "grounded" },
  ideas: [
    {
      title: "Try a smaller validation slice",
      rationale: "It reduces experiment cost.",
      suggested_validation_metric: "accuracy@10",
      next_small_experiment: "Run one baseline comparison.",
    },
  ],
  errors: [{ section: "memory", message: "memory unavailable" }],
};

function mountPanel(options = {}) {
  return mount(AssistantWorkflowPanel, options);
}

describe("AssistantWorkflowPanel", () => {
  test("uses assistant workflow defaults", () => {
    const wrapper = mountPanel();

    expect(wrapper.find("#assistant-intent").element.value).toBe("auto");
    expect(wrapper.findAll("#assistant-intent option").map((option) => option.element.value)).toEqual([
      "auto",
      "search",
      "research",
    ]);
    expect(wrapper.find("#assistant-top-k").element.value).toBe("5");
  });

  test("submits query settings to the runner and emits success", async () => {
    const runAssistant = vi.fn().mockResolvedValue(assistantResponse);
    const wrapper = mountPanel({ props: { runAssistant } });

    await wrapper.find("#assistant-query").setValue("graph reconstruction from papers");
    await wrapper.find("#assistant-intent").setValue("search");
    await wrapper.find("#assistant-top-k").setValue("8");
    await wrapper.find("form.assistant-form").trigger("submit.prevent");

    expect(runAssistant).toHaveBeenCalledWith({
      query: "graph reconstruction from papers",
      intent: "search",
      top_k: 8,
    });
    expect(wrapper.emitted("success")).toEqual([[assistantResponse]]);
  });

  test("renders assistant workflow response details", async () => {
    const wrapper = mountPanel({
      props: {
        runAssistant: vi.fn().mockResolvedValue(assistantResponse),
      },
    });

    await wrapper.find("#assistant-query").setValue("local evidence with discovery");
    await wrapper.find("form.assistant-form").trigger("submit.prevent");

    const text = wrapper.text();
    expect(text).toContain("mode: advanced");
    expect(text).toContain("route: advanced_search");
    expect(text).toContain("72%");
    expect(text).toContain("I can search with local context and discovery together.");
    expect(text).toContain("Review the recommended papers.");
    expect(text).toContain("Review top papers");
    expect(text).toContain("Upload selected PDFs");
    expect(text).toContain("memory: memory unavailable");
    expect(text).toContain("Try a smaller validation slice");
    expect(text).toContain("It reduces experiment cost.");
    expect(text).toContain("accuracy@10");
    expect(text).toContain("Run one baseline comparison.");
  });

  test("renders endpoint errors without emitting success", async () => {
    const runAssistant = vi.fn().mockRejectedValue(new Error("assistant endpoint unavailable"));
    const wrapper = mountPanel({ props: { runAssistant } });

    await wrapper.find("#assistant-query").setValue("will fail");
    await wrapper.find("form.assistant-form").trigger("submit.prevent");

    expect(wrapper.text()).toContain("assistant endpoint unavailable");
    expect(wrapper.emitted("success")).toBeUndefined();
  });

  test("disables submit and avoids runner calls when research intent is selected", async () => {
    const runAssistant = vi.fn().mockResolvedValue(assistantResponse);
    const wrapper = mountPanel({ props: { runAssistant } });

    await wrapper.find("#assistant-query").setValue("research idea from experiment logs");
    await wrapper.find("#assistant-intent").setValue("research");
    await wrapper.find("form.assistant-form").trigger("submit.prevent");

    expect(wrapper.find("button[type='submit']").element.disabled).toBe(true);
    expect(wrapper.text()).toContain("Structured experiment logs stay in the Idea Assistant section below");
    expect(runAssistant).not.toHaveBeenCalled();
    expect(wrapper.emitted("success")).toBeUndefined();
  });
});
