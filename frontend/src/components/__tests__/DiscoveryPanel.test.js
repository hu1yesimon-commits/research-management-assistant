import { describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";

import DiscoveryPanel from "../DiscoveryPanel.vue";

describe("DiscoveryPanel", () => {
  test("renders candidates even when optional fields are missing", () => {
    const wrapper = mount(DiscoveryPanel, {
      props: {
        discovery: {
          enabled: true,
          candidates: [
            {
              paper: {
                paper_id: "candidate-1",
                title: "Sparse Candidate",
              },
              judgement: {},
            },
          ],
          error: null,
        },
      },
    });

    expect(wrapper.text()).toContain("Sparse Candidate");
    expect(wrapper.text()).toContain("candidate-1");
  });
});
