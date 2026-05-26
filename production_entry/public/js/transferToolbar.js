import { ref } from "vue";

/** Board kind → transfer API scope (matches transfer_logistics.BOARD_KIND_TO_SCOPE). */
export const TRANSFER_BOARD_KINDS = {
  production: "production",
  lamination: "lamination",
  printing_105: "printing_105",
  printed_bopp_film: "printed_bopp_film",
  slitting: "slitting",
  rewinding: "rewinding",
  sheet_cutting: "sheet_cutting",
  box_bag: "box_bag",
};

export function useTransferToolbar(boardKind) {
  const showTransferDialog = ref(false);
  const transferPrefill = ref({});

  function openTransferDialog(prefill = {}) {
    transferPrefill.value = { ...prefill };
    showTransferDialog.value = true;
  }

  function closeTransferDialog() {
    showTransferDialog.value = false;
  }

  function buildFilterContext(ctx) {
    return {
      board_kind: boardKind,
      view_scope: ctx.viewScope || "daily",
      date: ctx.filterOrderDate || "",
      week: ctx.filterWeek || "",
      month: ctx.filterMonth || "",
      unit: ctx.filterUnit || "",
      party_code: ctx.filterPartyCode || "",
      customer: ctx.filterCustomer || "",
    };
  }

  return {
    showTransferDialog,
    transferPrefill,
    openTransferDialog,
    closeTransferDialog,
    buildFilterContext,
  };
}
