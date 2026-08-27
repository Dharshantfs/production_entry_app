/** GSM Production Entry — SPR Tools helpers (read-only: never creates SPR). */

import { openSprBundlePackagingDialog } from "./spr_bundle_packaging_dialog.js";
import { openSprManualJobDialog } from "./spr_manual_job_dialog.js";
import { openSprTrialOrderDialog } from "./spr_trial_order_dialog.js";
import "./spr_label.js";

async function loadSprDocForGsm(sprName) {
	if (production_entry.spr_label && typeof production_entry.spr_label.load_spr_doc === "function") {
		return production_entry.spr_label.load_spr_doc(sprName);
	}
	const res = await frappe.call({
		method: "production_entry.production_planning.unified_production_entry_api.get_gsm_spr_doc",
		args: { spr_name: sprName },
	});
	return res.message || null;
}

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

export async function gsmOpenTrailOrder(opts, onSuccess) {
	opts = opts && typeof opts === "object" ? opts : { ppId: opts };
	const unit = String(opts.unit || "").trim();
	if (!unit) {
		frappe.msgprint(__("Open the GSM shift (unit) first."));
		return;
	}
	openSprTrialOrderDialog({
		unit,
		runDate: opts.runDate,
		shift: opts.shift,
		operator: opts.operator,
		supervisor: opts.supervisor,
		onSuccess: (result) => {
			if (typeof onSuccess === "function") {
				onSuccess(result);
			}
			if (typeof opts.onSuccess === "function") {
				opts.onSuccess(result);
			}
		},
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

/** Print production label — delegates to shared desk SPR label flow. */
export async function gsmPrintRollLabel(sprName, sprItemRowName, gridRow = null) {
	if (!sprName) {
		frappe.msgprint(__("Create SPRs first."));
		return;
	}
	if (!sprItemRowName) {
		frappe.msgprint(__("Save Row first to enable the label."));
		return;
	}
	if (gridRow && gridRow.produced_length_mtrs) {
		try {
			await frappe.call({
				method:
					"production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_set_item_row_lock",
				args: {
					spr_name: sprName,
					row_name: sprItemRowName,
					locked: 1,
					produced_length_mtrs: gridRow.produced_length_mtrs,
					produced_gsm: gridRow.produced_gsm,
					gross_weight: gridRow.gross_weight,
					net_weight: gridRow.net_weight,
				},
			});
		} catch (e) {
			// print uses saved SPR row
		}
	}
	try {
		if (production_entry.spr_label && typeof production_entry.spr_label.print_roll === "function") {
			await production_entry.spr_label.print_roll(sprName, sprItemRowName);
			return;
		}
		frappe.msgprint(__("Label print helper not loaded."));
	} catch (e) {
		console.error("gsmPrintRollLabel", e);
		frappe.msgprint(__("Could not open label print."));
	}
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
	const doc = await loadSprDocForGsm(sprName);
	if (!doc) {
		frappe.msgprint(__("Could not load SPR for bundle label print."));
		return;
	}
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

/** Print QC / approval label — same format as desk SPR approval label. */
export async function gsmPrintQcLabel(sprName, sprItemRowName, gridRow = null, extra = {}) {
	if (!sprName) {
		frappe.msgprint(__("Create SPRs first."));
		return;
	}
	const options = {
		operator: extra.operator || "",
		supervisor: extra.supervisor || "",
		batch_no: (gridRow && gridRow.batch_no) || extra.batch_no || "",
	};
	if (!sprItemRowName && !options.batch_no) {
		frappe.msgprint(__("Save Row first to enable the QC label."));
		return;
	}
	try {
		if (production_entry.spr_label && typeof production_entry.spr_label.print_qc === "function") {
			await production_entry.spr_label.print_qc(sprName, sprItemRowName, options);
			return;
		}
		frappe.msgprint(__("QC label print helper not loaded."));
	} catch (e) {
		console.error("gsmPrintQcLabel", e);
		frappe.msgprint(__("Could not open QC label print."));
	}
}

/** Print wastage label — shared desk SPR wastage print functions only. */
export async function gsmPrintWastageLabel(sprName, childRowName, tableField, rowData) {
	if (!production_entry.spr_label || typeof production_entry.spr_label.print_wastage !== "function") {
		frappe.msgprint(__("Wastage label print helper not loaded."));
		return;
	}
	await production_entry.spr_label.print_wastage(sprName, childRowName, tableField, rowData);
}

/** Start Round Cutting GSM Test — same redirect as desk SPR Quality Check. */
export async function gsmOpenGsmTesting(ppId, jobId) {
	return gsmOpenRoundCuttingGsmTesting(ppId, jobId);
}

/** Start Round Cutting GSM Test — same as SPR. */
export async function gsmOpenRoundCuttingGsmTesting(ppId, jobId) {
	const sprName = await findSprForGsm(ppId, true);
	if (!sprName) {
		noSprMessage();
		return;
	}
	const qc = production_entry.spr_quality_check;
	if (qc && typeof qc.openSprRoundCuttingGsmTesting === "function") {
		await qc.openSprRoundCuttingGsmTesting(sprName, jobId);
		return;
	}
	if (qc && typeof qc.openSprGsmTesting === "function") {
		await qc.openSprGsmTesting(sprName, jobId);
		return;
	}
	frappe.msgprint(__("Quality Check helper not loaded."));
}

/** Start Patty Cutting GSM Test — same as SPR. */
export async function gsmOpenPattyCuttingGsmTesting(ppId, jobId) {
	const sprName = await findSprForGsm(ppId, true);
	if (!sprName) {
		noSprMessage();
		return;
	}
	const qc = production_entry.spr_quality_check;
	if (qc && typeof qc.openSprPattyCuttingGsmTesting === "function") {
		await qc.openSprPattyCuttingGsmTesting(sprName, jobId);
		return;
	}
	frappe.msgprint(__("Quality Check helper not loaded."));
}

/** Start Tensile Testing — same redirect as desk SPR Quality Check. */
export async function gsmOpenTensileTesting(ppId, jobId) {
	const sprName = await findSprForGsm(ppId, true);
	if (!sprName) {
		noSprMessage();
		return;
	}
	const qc = production_entry.spr_quality_check;
	if (qc && typeof qc.openSprTensileTesting === "function") {
		await qc.openSprTensileTesting(sprName, jobId);
		return;
	}
	frappe.msgprint(__("Quality Check helper not loaded."));
}

/** Fix No. of Shaft = 0 on draft SPR roll lines. */
export async function gsmBackfillShaftNumbers(ppId) {
	const sprName = await findSprForGsm(ppId, true);
	if (!sprName) {
		noSprMessage();
		return null;
	}
	const res = await frappe.call({
		method:
			"production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.backfill_spr_roll_shaft_numbers",
		args: { spr_name: sprName },
	});
	const fixed = cint(res?.message?.rows_fixed);
	frappe.show_alert({
		message: fixed
			? __("Fixed {0} roll row(s) on {1}", [fixed, sprName])
			: __("No shaft numbers needed fixing on {0}", [sprName]),
		indicator: fixed ? "green" : "blue",
	});
	return res.message || {};
}

function cint(v) {
	const n = parseInt(v, 10);
	return Number.isFinite(n) ? n : 0;
}
