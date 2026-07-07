import { describe, expect, test, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

import SessionChatPanel from "../SessionChatPanel.vue";

describe("SessionChatPanel", () => {
  test("renders history and submits one idempotent turn", async () => {
    const runTurn = vi.fn().mockResolvedValue({
      turn_id: "turn-2",
      status: "completed",
      assistant_message: "I found fresh papers.",
    });
    const wrapper = mount(SessionChatPanel, {
      props: {
        messages: [
          { id: 1, role: "user", content: { text: "Earlier question" } },
          { id: 2, role: "assistant", content: { assistant_message: "Earlier answer" } },
          { id: 3, role: "agent", content: { text: "internal trace" } },
        ],
        runTurn,
      },
    });

    await wrapper.find("textarea").setValue("Find fresh papers");
    await wrapper.find("form").trigger("submit.prevent");

    expect(runTurn).toHaveBeenCalledWith(
      expect.objectContaining({
        message: "Find fresh papers",
        idempotency_key: expect.any(String),
      }),
    );
    expect(wrapper.text()).toContain("Earlier answer");
    expect(wrapper.text()).not.toContain("internal trace");
  });

  test("reuses the same idempotency key when retrying the same failed draft", async () => {
    const runTurn = vi
      .fn()
      .mockRejectedValueOnce(new Error("temporary failure"))
      .mockResolvedValueOnce({
        turn_id: "turn-3",
        status: "completed",
        assistant_message: "Recovered",
      });

    const randomUUID = vi.fn().mockReturnValue("retry-key");
    vi.stubGlobal("crypto", { randomUUID });

    const wrapper = mount(SessionChatPanel, {
      props: {
        messages: [],
        runTurn,
      },
    });

    await wrapper.find("textarea").setValue("Retry me");
    await wrapper.find("form").trigger("submit.prevent");
    await flushPromises();
    await wrapper.find("form").trigger("submit.prevent");

    expect(runTurn).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        message: "Retry me",
        idempotency_key: "retry-key",
      }),
    );
    expect(runTurn).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        message: "Retry me",
        idempotency_key: "retry-key",
      }),
    );
    expect(randomUUID).toHaveBeenCalledTimes(1);
  });
});
