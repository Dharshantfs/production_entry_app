/** GSM Production Entry — SPR Tools helpers (read-only: never creates SPR). */

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
			"No SPR found for this Production Plan. Create/open SPR from Production Table — GSM Production Entry does not create SPR."
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

export async function gsmToggleBundlePackaging(ppId) {
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

function cint(v) {
	const n = parseInt(v, 10);
	return Number.isFinite(n) ? n : 0;
}
