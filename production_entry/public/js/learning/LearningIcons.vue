<template>
  <svg
    v-if="name === 'plan'"
    class="pl-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    aria-hidden="true"
  >
    <rect x="4" y="3" width="16" height="18" rx="2" />
    <path d="M8 8h8M8 12h8M8 16h5" />
  </svg>
  <svg
    v-else-if="name === 'produce'"
    class="pl-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </svg>
  <svg
    v-else-if="name === 'transfer'"
    class="pl-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    aria-hidden="true"
  >
    <path d="M2 12h14M12 6l6 6-6 6" />
    <rect x="16" y="8" width="6" height="8" rx="1" />
  </svg>
  <svg
    v-else-if="name === 'despatch'"
    class="pl-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    aria-hidden="true"
  >
    <path d="M12 3v12" />
    <path d="M8 11l4 4 4-4" />
    <rect x="5" y="17" width="14" height="4" rx="1" />
  </svg>
  <svg
    v-else
    class="pl-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="9" />
  </svg>
</template>

<script setup>
defineProps({
  name: { type: String, default: "plan" },
});
</script>

<style scoped>
.pl-icon {
  width: 1.25rem;
  height: 1.25rem;
  flex-shrink: 0;
}
</style>
