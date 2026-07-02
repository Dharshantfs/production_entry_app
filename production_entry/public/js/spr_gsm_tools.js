/** GSM Production Entry — SPR Tools helpers. */

import { openSprManualJobDialog } from "./spr_manual_job_dialog.js";

export async function ensureDraftSprForGsm(ppId, planningItemNames, unit, runDate, shift) {
	const res = await frappe.call({
		method: "production_entry.production_planning.unified_production_entry_api.ensure_draft_spr_for_pp",
		args: {
			pp_id: ppId,
			planning_sheet_item_names: JSON.stringify(planningItemNames),
			unit,
			run_date: runDate,
			shift,
		},
	});
	const msg = res.message || {};
	if (msg.status !== "ok" || !msg.spr_name) {
		const err = msg.message || __("Could not open draft SPR.");
		frappe.msgprint(err);
		return null;
	}
	return msg.spr_name;
}

export function openSprForm(sprName) {
	if (!sprName) {
		return;
	}
	frappe.set_route("Form", "Shaft Production Run", sprName);
}

export async function gsmOpenManualJob(ppId, planningItemNames, unit, runDate, shift, onSuccess) {
	const sprName = await ensureDraftSprForGsm(ppId, planningItemNames, unit, runDate, shift);
	if (!sprName) {
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

export async function gsmOpenTrailOrder(ppId, planningItemNames, unit, runDate, shift) {
	const sprName = await ensureDraftSprForGsm(ppId, planningItemNames, unit, runDate, shift);
	if (sprName) {
		openSprForm(sprName);
		frappe.show_alert({
			message: __("Open SPR → Tools → Trail Order for this run."),
			indicator: "blue",
		});
	}
}

export async function gsmToggleBundlePackaging(ppId, planningItemNames, unit, runDate, shift) {
	const sprName = await ensureDraftSprForGsm(ppId, planningItemNames, unit, runDate, shift);
	if (!sprName) {
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

export async function gsmOpenRmBatches(ppId, planningItemNames, unit, runDate, shift) {
	const sprName = await ensureDraftSprForGsm(ppId, planningItemNames, unit, runDate, shift);
	if (sprName) {
		openSprForm(sprName);
		frappe.show_alert({
			message: __("Open SPR → Tools → Select RM batches."),
			indicator: "blue",
		});
	}
}

function cint(v) {
	const n = parseInt(v, 10);
	return Number.isFinite(n) ? n : 0;
}
