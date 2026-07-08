/** GSM Production Entry — SPR Tools helpers (read-only: never creates SPR). */

import { openSprBundlePackagingDialog } from "./spr_bundle_packaging_dialog.js";
import { openSprManualJobDialog } from "./spr_manual_job_dialog.js";

export async function findSprForGsm(ppId, preferDraft = true) {
	const res = await frappe.call({
		method: "production_entry.production_planning.unified_production_entry_api.get_spr_for_pp",
		args: { pp_id: ppId, prefer_draft: preferDraft ? 1 : 0 },
	});
	return (res.message || {}).spr_name || null;
}

export function openSprForm(sprName) {
	if (!sprName) {
		return;
	}
	frappe.set_route("Form", "Shaft Production Run", sprName);
}

function noSprMessage() {
	frappe.msgprint(
		__(
			"No SPR found for this Production Plan. Use Create SPRs in GSM Production Entry, or create from Production Table."
		)
	);
}

export async function gsmOpenManualJob(ppId, _planningItemNames, _unit, _runDate, _shift, onSuccess) {
	const sprName = await findSprForGsm(ppId, true);
	if (!sprName) {
		noSprMessage();
		return;
	}
	openSprManualJobDialog({
		sprName,
		onSuccess: () => {
			if (typeof onSuccess === "function") {
				onSuccess(sprName);
			}
		},
	});
}

export async function gsmOpenTrailOrder(ppId) {
	const sprName = await findSprForGsm(ppId, true);
	if (!sprName) {
		noSprMessage();
		return;
	}
	openSprForm(sprName);
	frappe.show_alert({
		message: __("Open SPR → Tools → Trail Order for this run."),
		indicator: "blue",
	});
}

/** Open Bundle packaging for GSM — creates fresh SPR rolls + one GSM summary row. */
export async function gsmOpenBundlePackaging(ppId, onSuccess, options = {}) {
	const sprName = await findSprForGsm(ppId, true);
	if (!sprName) {
		noSprMessage();
		return;
	}
	openSprBundlePackagingDialog({
		sprName,
		gsmMode: true,
		ppId,
		onSuccess: (result) => {
			if (typeof onSuccess === "function") {
				onSuccess(result, sprName);
			}
		},
	});
}

/** Toggle SPR custom_use_bundle_packaging_on_submit (Manufacture SE on submit). */
export async function gsmToggleBundleSeOnSubmit(ppId) {
	const sprName = await findSprForGsm(ppId, true);
	if (!sprName) {
		noSprMessage();
		return;
	}
	const dbRes = await frappe.db.get_value(
		"Shaft Production Run",
		sprName,
		"custom_use_bundle_packaging_on_submit"
	);
	const cur = cint(dbRes?.message?.custom_use_bundle_packaging_on_submit);
	const next = cur ? 0 : 1;
	await frappe.call({
		method:
			"production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_set_bundle_packaging_on_submit",
		args: { shaft_production_run: sprName, enabled: next },
	});
	frappe.show_alert({
		message: next ? __("Bundle SE on Submit: ON") : __("Bundle SE on Submit: OFF"),
		indicator: "green",
	});
}

export async function gsmOpenRmBatches(ppId) {
	const sprName = await findSprForGsm(ppId, true);
	if (!sprName) {
		noSprMessage();
		return;
	}
	openSprForm(sprName);
	frappe.show_alert({
		message: __("Open SPR → Tools → Select RM batches."),
		indicator: "blue",
	});
}

/** Print production label for a saved SPR item row (same flow as desk SPR). */
export async function gsmPrintRollLabel(sprName, sprItemRowName, gridRow = null) {
	if (!sprName) {
		frappe.msgprint(__("Create SPRs first."));
		return;
	}
	if (!sprItemRowName) {
		frappe.msgprint(__("Save Row first to enable the label."));
		return;
	}
	if (typeof frappe.generate_sticker_flow !== "function") {
		await import("./custom_print_sticker.js");
	}
	await frappe.model.with_doc("Shaft Production Run", sprName);
	const doc = frappe.get_doc("Shaft Production Run", sprName);
	(doc.items || []).forEach((itemRow) => {
		const isTarget = itemRow.name === sprItemRowName;
		const len =
			itemRow.custom_produced_length_mtrs ||
			itemRow.produced_length_mtrs ||
			(isTarget && gridRow ? gridRow.produced_length_mtrs : null);
		if (len && !itemRow.custom_produced_length_mtrs) {
			itemRow.custom_produced_length_mtrs = len;
		}
		if (len && !itemRow.produced_length_mtrs) {
			itemRow.produced_length_mtrs = len;
		}
		frappe.model.add_to_locals(itemRow);
	});
	const frm = { doc };
	if (typeof frappe.generate_sticker_flow === "function") {
		frappe.generate_sticker_flow(sprItemRowName, frm);
		return;
	}
	frappe.msgprint(__("Label print module could not be loaded."));
}

/** Print bundle sticker label (Bundle Stickers row — not single-roll label). */
export async function gsmPrintBundleLabel(sprName, gridRow = null) {
	if (!sprName) {
		frappe.msgprint(__("Create SPRs first."));
		return;
	}
	if (!gridRow || !gridRow.batch_no) {
		frappe.msgprint(__("Bundle batch is missing."));
		return;
	}
	if (typeof frappe.generate_bundle_sticker_flow !== "function") {
		await import("./custom_print_sticker.js");
	}
	await frappe.model.with_doc("Shaft Production Run", sprName);
	const doc = frappe.get_doc("Shaft Production Run", sprName);
	const bundleBatch = String(gridRow.batch_no || "").trim();
	let sticker = (doc.bundle_stickers || []).find((bs) => String(bs.batch_no || "").trim() === bundleBatch);
	if (!sticker && bundleBatch) {
		try {
			const res = await frappe.db.get_list("Bundle Stickers", {
				filters: { parent: sprName, batch_no: bundleBatch },
				fields: ["name", "batch_no", "combination", "roll_numbers", "rolls_per_bundle", "produced_length_mtrs", "sticker_width", "sticker_bundle_gross_weight_kg", "sticker_bundle_weight"],
				limit: 1,
			});
			sticker = res?.[0] || null;
		} catch (e) {
			sticker = null;
		}
	}
	const frm = { doc };
	if (typeof frappe.generate_bundle_sticker_flow === "function") {
		frappe.generate_bundle_sticker_flow(sticker, frm, gridRow);
		return;
	}
	frappe.msgprint(__("Bundle label print module could not be loaded."));
}

const _WASTAGE_LABEL_FN_CANDIDATES = [
	"print_wastage_label_flow",
	"generate_wastage_sticker_flow",
	"print_patty_wastage_label",
];

/** Print wastage label for Running Patty or Roll Waste child row on SPR. */
export async function gsmPrintWastageLabel(sprName, childRowName, tableField) {
	if (!sprName) {
		frappe.msgprint(__("Create SPRs first."));
		return;
	}
	if (!childRowName) {
		frappe.msgprint(__("Save the wastage row first."));
		return;
	}
	tableField = tableField || "custom_running_patty_wastage";

	for (const fnName of _WASTAGE_LABEL_FN_CANDIDATES) {
		if (typeof frappe[fnName] === "function") {
			await frappe.model.with_doc("Shaft Production Run", sprName);
			const doc = frappe.get_doc("Shaft Production Run", sprName);
			frappe[fnName](childRowName, { doc }, tableField);
			return;
		}
	}

	if (typeof frappe.generate_sticker_flow !== "function") {
		await import("./custom_print_sticker.js");
	}
	await frappe.model.with_doc("Shaft Production Run", sprName);
	const doc = frappe.get_doc("Shaft Production Run", sprName);
	const rows = doc[tableField] || [];
	const row = rows.find((r) => r.name === childRowName);
	if (!row) {
		frappe.msgprint(__("Wastage row not found on SPR."));
		return;
	}
	if (typeof frappe.generate_sticker_flow === "function" && row.batch_no) {
		const linkedItem = (doc.items || []).find((it) => it.batch_no === row.batch_no);
		if (linkedItem) {
			frappe.generate_sticker_flow(linkedItem.name, { doc });
			return;
		}
	}
	frappe.msgprint(
		__(
			"Wastage label print is not available in GSM yet. Open desk SPR for Print Label on this row."
		)
	);
}

function cint(v) {
	const n = parseInt(v, 10);
	return Number.isFinite(n) ? n : 0;
}
