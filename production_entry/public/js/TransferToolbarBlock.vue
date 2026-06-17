<template>
  <button
    type="button"
    class="cc-transfer-btn"
    :class="{ 'cc-btn-frozen': disabled }"
    :disabled="disabled"
    title="Transfer rows (SPR done)"
    @click="open"
  >
    Transfer
  </button>
  <TransferDialog
    v-model="showTransferDialog"
    :board-kind="boardKind"
    :filter-context="filterContext"
    :prefill="transferPrefill"
    @submitted="onSubmitted"
  />
</template>

<script setup>
import { computed } from "vue";
import TransferDialog from "./TransferDialog.vue";
import { useTransferToolbar } from "./transferToolbar.js";

const props = defineProps({
  boardKind: { type: String, required: true },
  filterContext: { type: Object, default: () => ({}) },
  disabled: { type: Boolean, default: false },
});

const emit = defineEmits(["submitted"]);

const { showTransferDialog, transferPrefill, openTransferDialog } = useTransferToolbar(props.boardKind);

const filterContext = computed(() => props.filterContext || {});

function open() {
  if (props.disabled) return;
  openTransferDialog({});
}

function onSubmitted() {
  emit("submitted");
}
</script>

<style scoped>
.cc-transfer-btn {
  background: #0ea5e9;
  color: #fff;
  border: 1px solid #0284c7;
  padding: 6px 12px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 12px;
  cursor: pointer;
}
.cc-transfer-btn:hover:not(:disabled) {
  background: #0284c7;
}
.cc-transfer-btn:disabled,
.cc-btn-frozen {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
