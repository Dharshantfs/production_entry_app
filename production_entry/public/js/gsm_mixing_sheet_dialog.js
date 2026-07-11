/* global frappe, __ */

function mixingApi() {
	return window.production_entry?.spr_mixing_sheet || {};
}

/**
 * Open mixing sheet from GSM Production Entry — one sheet per shift session + unit.
 */
export async function openGsmMixingSheetDialog(opts = {}) {
	const unit = (opts.custom_unit || opts.headerUnit || "").trim();
	const run_date = opts.run_date || opts.runDate || "";
	const shift = opts.shift || "";
	const gsm_shift_session = opts.gsm_shift_session || opts.shiftSessionId || "";
	const { openSprMixingSheet, isMixingExcludedUnit } = mixingApi();

	if (!openSprMixingSheet) {
		frappe.msgprint(__("Mixing Sheet module not loaded. Run bench build --app production_entry."));
		return;
	}
	if (!unit) {
		frappe.msgprint(__("Select a unit first."));
		return;
	}
	if (!run_date || !shift) {
		frappe.msgprint(__("Set Run Date and Shift first."));
		return;
	}
	if (isMixingExcludedUnit && isMixingExcludedUnit(unit)) {
		frappe.msgprint(__("Mixing Sheet is not available for bag-making lines."));
		return;
	}

	await openSprMixingSheet({
		custom_unit: unit,
		run_date,
		shift,
		gsm_shift_session,
		shift_only: true,
		title_label: `${run_date} · ${shift} · ${unit}`,
		on_saved: opts.on_saved,
	});
}
