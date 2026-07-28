import { describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";

import AgentTracePanel from "../AgentTracePanel.vue";

describe("AgentTracePanel", () => {
  test("renders bounded plan, agent runs, and typed errors inside collapsed details", async () => {
    const wrapper = mount(AgentTracePanel, {
      props: {
        plan: {
          plan_type: "research_then_idea",
          goal: "Find newer evidence and propose ideas",
        },
        agentRuns: [
          { agent_name: "research", action: "recommend_papers", status: "completed" },
          { agent_name: "idea", action: "generate_ideas", status: "skipped" },
        ],
        errors: [{ agent_name: "idea", stage: "dispatch", message: "idea unavailable" }],
      },
    });

    expect(wrapper.text()).toContain("Plan: research_then_idea");
    expect(wrapper.text()).toContain("Find newer evidence and propose ideas");
    expect(wrapper.text()).not.toContain("recommend_papers");

    await wrapper.get("summary").trigger("click");

    expect(wrapper.text()).toContain("research");
    expect(wrapper.text()).toContain("completed");
    expect(wrapper.text()).toContain("idea");
    expect(wrapper.text()).toContain("skipped");
    expect(wrapper.text()).toContain("idea: idea unavailable");
  });
});
