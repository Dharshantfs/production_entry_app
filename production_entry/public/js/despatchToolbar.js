import { ref } from "vue";

/** Board kind → color-chart scope (same as transfer_logistics.BOARD_KIND_TO_SCOPE). */
export const DESPATCH_BOARD_KINDS = {
  production: "production",
  lamination: "lamination",
  printing_105: "printing_105",
  printed_bopp_film: "printed_bopp_film",
  slitting: "slitting",
  rewinding: "rewinding",
  sheet_cutting: "sheet_cutting",
  box_bag: "box_bag",
  w_cut_d_cut: "w_cut_d_cut",
};

export function useDespatchToolbar(boardKind) {
  const showDespatchDialog = ref(false);
  const despatchPrefill = ref({});

  function openDespatchDialog(prefill = {}) {
    despatchPrefill.value = { ...prefill };
    showDespatchDialog.value = true;
  }

  function closeDespatchDialog() {
    showDespatchDialog.value = false;
  }

  return {
    showDespatchDialog,
    despatchPrefill,
    openDespatchDialog,
    closeDespatchDialog,
  };
}
