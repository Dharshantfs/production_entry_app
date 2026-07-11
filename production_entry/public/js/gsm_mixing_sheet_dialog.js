/* global frappe, __ */

import { pickSessionSpr } from "./gsm_wastage_recycle_dialog.js";

function mixingApi() {
	return window.production_entry?.spr_mixing_sheet || {};
}

/**
 * Open mixing sheet from GSM Production Entry.
 * Always links to a specific SPR when session SPRs exist (per-order sheets).
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

	const sessionList = (opts.sessionSprList || []).filter((s) => s && s.spr_name);
	let sprRow = null;

	if (sessionList.length === 1) {
		sprRow = sessionList[0];
	} else if (sessionList.length > 1) {
		sprRow = await pickSessionSpr(sessionList, opts);
		if (!sprRow) {
			return;
		}
	}

	await openSprMixingSheet({
		custom_unit: unit,
		run_date,
		shift,
		gsm_shift_session,
		spr_name: sprRow?.spr_name || "",
		order_code: sprRow?.order_code || "",
		title_label: sprRow
			? `${sprRow.order_code || ""} · ${sprRow.spr_name}`
			: `${run_date} · ${shift} · ${unit}`,
		on_saved: opts.on_saved,
	});
}

export async function openGsmMixingSheetForSpr(opts = {}) {
	const sprRow = await pickSessionSpr(opts.sessionSprList);
	if (!sprRow) return;
	const { openSprMixingSheet } = mixingApi();
	if (!openSprMixingSheet) return;
	await openSprMixingSheet({
		...opts,
		spr_name: sprRow.spr_name,
		order_code: sprRow.order_code || "",
		title_label: `${sprRow.order_code || ""} · ${sprRow.spr_name}`,
	});
}
