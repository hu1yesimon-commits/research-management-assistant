<template>
  <form class="query-form" @submit.prevent="submitForm">
    <div class="query-form__header">
      <div>
        <h2>Research Query</h2>
        <p>Primary frontend entrypoint: <code>POST /research/query</code></p>
      </div>
      <button class="button button--primary" type="submit" :disabled="loading">
        {{ loading ? "Searching..." : "Search" }}
      </button>
    </div>

    <label class="field">
      <span>Query</span>
      <textarea
        id="query"
        v-model.trim="form.query"
        rows="3"
        placeholder="Ask for grounded knowledge, recommended reading, or both."
      />
    </label>

    <div class="query-form__grid">
      <label class="field">
        <span>Mode</span>
        <select id="mode" v-model="form.mode">
          <option value="basic">basic</option>
          <option value="advanced">advanced</option>
        </select>
      </label>

      <label class="field">
        <span>Top K</span>
        <input id="top-k" v-model.number="form.top_k" type="number" min="1" max="20" />
      </label>
    </div>

    <div class="query-form__toggles">
      <label class="checkbox">
        <input id="include-discovery" v-model="form.include_discovery" type="checkbox" />
        <span>Include discovery candidates</span>
      </label>

      <label class="checkbox">
        <input id="include-knowledge" v-model="form.include_knowledge" type="checkbox" />
        <span>Include knowledge answer</span>
      </label>
    </div>
  </form>
</template>

<script setup>
import { reactive } from "vue";

defineProps({
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["submit"]);

const form = reactive({
  query: "",
  mode: "basic",
  include_discovery: true,
  include_knowledge: true,
  top_k: 5,
});

function submitForm() {
  emit("submit", {
    query: form.query,
    mode: form.mode,
    include_discovery: form.include_discovery,
    include_knowledge: form.include_knowledge,
    top_k: form.top_k,
  });
}
</script>
