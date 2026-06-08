import { describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";

import QueryForm from "../QueryForm.vue";

describe("QueryForm", () => {
  test("uses the requested MVP defaults", () => {
    const wrapper = mount(QueryForm);

    expect(wrapper.find("#mode").element.value).toBe("basic");
    expect(wrapper.find("#include-discovery").element.checked).toBe(true);
    expect(wrapper.find("#include-knowledge").element.checked).toBe(true);
    expect(wrapper.find("#top-k").element.value).toBe("5");
  });
});
