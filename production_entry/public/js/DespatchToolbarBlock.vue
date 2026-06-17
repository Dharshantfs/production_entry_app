<template>
  <button
    type="button"
    class="cc-despatch-btn"
    :class="{ 'cc-btn-frozen': disabled }"
    :disabled="disabled"
    title="Despatch rows (movement Despatch, SPR submitted)"
    @click="open"
  >
    Despatch
  </button>
  <DespatchDialog
    v-model="showDespatchDialog"
    :board-kind="boardKind"
    :filter-context="filterContext"
    :prefill="despatchPrefill"
    @submitted="onSubmitted"
  />
</template>

<script setup>
import { computed } from "vue";
import DespatchDialog from "./DespatchDialog.vue";
import { useDespatchToolbar } from "./despatchToolbar.js";

const props = defineProps({
  boardKind: { type: String, required: true },
  filterContext: { type: Object, default: () => ({}) },
  disabled: { type: Boolean, default: false },
});

const emit = defineEmits(["submitted"]);

const { showDespatchDialog, despatchPrefill, openDespatchDialog } = useDespatchToolbar(props.boardKind);

const filterContext = computed(() => props.filterContext || {});

function open() {
  if (props.disabled) return;
  openDespatchDialog({});
}

function onSubmitted() {
  emit("submitted");
}
</script>

<style scoped>
.cc-despatch-btn {
  background: #16a34a;
  color: #fff;
  border: 1px solid #15803d;
  padding: 6px 12px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 12px;
  cursor: pointer;
}
.cc-despatch-btn:hover:not(:disabled) {
  background: #15803d;
}
.cc-despatch-btn:disabled,
.cc-btn-frozen {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
