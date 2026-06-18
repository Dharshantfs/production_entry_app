/** Shared Production Plan print preview for all board order tables. */

export const PP_PRINT_FORMAT = "Order Sheet format";

export function productionPlanPrintPreviewUrl(ppId) {
	const id = String(ppId || "").trim();
	return `/printview?doctype=${encodeURIComponent("Production Plan")}&name=${encodeURIComponent(id)}&format=${encodeURIComponent(PP_PRINT_FORMAT)}&trigger_print=0`;
}

export function openProductionPlanPrintPreview(ppId) {
	const id = String(ppId || "").trim();
	if (!id) {
		return false;
	}
	window.open(productionPlanPrintPreviewUrl(id), "_blank");
	return true;
}

/**
 * Open PP print preview using row pp_id or resolve via planning sheet API.
 */
export async function resolveAndOpenProductionPlanPrintPreview({
	planningSheetName,
	salesOrderItem = null,
	planningSheetItem = null,
	directPpId = null,
	missingSheetMessage = "Planning Sheet not found",
}) {
	if (!planningSheetName) {
		frappe.msgprint(__(missingSheetMessage));
		return;
	}
	let ppId = String(directPpId || "").trim();
	if (ppId) {
		openProductionPlanPrintPreview(ppId);
		return;
	}
	try {
		const res = await frappe.call({
			method: "production_entry.production_planning.scheduler_api.get_planning_sheet_pp_id",
			args: {
				planning_sheet_name: planningSheetName,
				sales_order_item: salesOrderItem,
				planning_sheet_item: planningSheetItem,
			},
		});
		if (res.message && res.message.status === "ok") {
			ppId = String(res.message.pp_id || "").trim();
			if (ppId) {
				openProductionPlanPrintPreview(ppId);
			} else {
				frappe.msgprint(__("No Production Plan found"));
			}
		} else {
			frappe.msgprint(res.message?.message || __("Error"));
		}
	} catch (e) {
		frappe.msgprint(__("Error opening Production Plan"));
	}
}
