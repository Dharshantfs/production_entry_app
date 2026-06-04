<template>
  <button
    type="button"
    class="cc-despatch-btn"
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
});

const emit = defineEmits(["submitted"]);

const { showDespatchDialog, despatchPrefill, openDespatchDialog } = useDespatchToolbar(props.boardKind);

const filterContext = computed(() => props.filterContext || {});

function open() {
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
.cc-despatch-btn:hover {
  background: #15803d;
}
</style>
