<template>
  <section class="panel panel--full">
    <div class="panel__heading">
      <div>
        <h2>Session Chat</h2>
        <p>Default persistent session for multi-turn research coordination.</p>
      </div>
      <span class="badge" :class="isBusy ? 'badge--muted' : 'badge--active'">
        {{ isBusy ? "Running" : "Ready" }}
      </span>
    </div>

    <div class="chat-thread">
      <p v-if="!displayMessages.length" class="empty-state">
        Start the default session here. The latest assistant reply, plan trace, and active candidates stay attached to this chat.
      </p>

      <article
        v-for="message in displayMessages"
        :key="message.id"
        :class="['chat-message', `chat-message--${message.role}`]"
      >
        <p class="chat-message__role">{{ message.role === "user" ? "You" : "Assistant" }}</p>
        <p class="chat-message__body">{{ message.text }}</p>
      </article>
    </div>

    <form class="session-chat-form" @submit.prevent="submitTurn">
      <label class="field">
        <span>Message</span>
        <textarea
          id="session-chat-input"
          v-model.trim="draft"
          rows="4"
          placeholder="Ask for grounded help, fresh papers, or an idea based on your current experiment context."
        />
      </label>

      <div class="session-chat-form__actions">
        <button class="button button--primary" type="submit" :disabled="isSubmitDisabled">
          {{ isBusy ? "Running..." : "Send" }}
        </button>
      </div>
    </form>

    <div v-if="error" class="alert alert--danger session-chat-form__status">
      <strong>Session turn failed:</strong> {{ error }}
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  messages: {
    type: Array,
    default: () => [],
  },
  runTurn: {
    type: Function,
    required: true,
  },
});

const emit = defineEmits(["turn-completed", "turn-failed"]);

const draft = ref("");
const error = ref("");
const isBusy = ref(false);
const retryState = ref(null);

const displayMessages = computed(() =>
  props.messages
    .filter((message) => message.role === "user" || message.role === "assistant")
    .map((message) => ({
      id: message.id,
      role: message.role,
      text: message.content?.text || message.content?.assistant_message || "",
    }))
    .filter((message) => message.text),
);

const isSubmitDisabled = computed(() => isBusy.value || !draft.value);

function nextIdempotencyKey() {
  if (retryState.value?.message === draft.value) {
    return retryState.value.key;
  }
  return crypto.randomUUID();
}

async function submitTurn() {
  if (isSubmitDisabled.value) {
    return;
  }

  isBusy.value = true;
  error.value = "";
  const message = draft.value;
  const idempotencyKey = nextIdempotencyKey();

  try {
    const response = await props.runTurn({
      message,
      idempotency_key: idempotencyKey,
    });
    retryState.value = null;
    draft.value = "";
    emit("turn-completed", response);
  } catch (requestError) {
    retryState.value = {
      key: idempotencyKey,
      message,
    };
    error.value = requestError.message || "Session turn failed";
    emit("turn-failed", requestError);
  } finally {
    isBusy.value = false;
  }
}
</script>
