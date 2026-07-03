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

/** Open real Bundle packaging dialog (job + width + gross/length apply). */
export async function gsmOpenBundlePackaging(ppId, onSuccess) {
	const sprName = await findSprForGsm(ppId, true);
	if (!sprName) {
		noSprMessage();
		return;
	}
	openSprBundlePackagingDialog({
		sprName,
		onSuccess: () => {
			if (typeof onSuccess === "function") {
				onSuccess(sprName);
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

function cint(v) {
	const n = parseInt(v, 10);
	return Number.isFinite(n) ? n : 0;
}
