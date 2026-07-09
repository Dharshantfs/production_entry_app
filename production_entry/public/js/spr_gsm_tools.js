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
			// sticker flow uses saved SPR row
		}
	}
	if (typeof frappe.generate_sticker_flow !== "function") {
		await import("./custom_print_sticker.js");
	}
	await frappe.model.withDoc("Shaft Production Run", sprName);
	const frm = { doc: frappe.get_doc("Shaft Production Run", sprName) };
	if (typeof frappe.generate_sticker_flow === "function") {
		frappe.generate_sticker_flow(sprItemRowName, frm);
		return;
	}
	if (
		production_entry.spr_roll_label_print &&
		typeof production_entry.spr_roll_label_print.open === "function"
	) {
		production_entry.spr_roll_label_print.open(sprName, sprItemRowName);
		return;
	}
	frappe.msgprint(__("Label print helper not loaded."));
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

	await frappe.model.with_doc("Shaft Production Run", sprName);
	const doc = frappe.get_doc("Shaft Production Run", sprName);
	const rows = doc[tableField] || [];
	const row = rows.find((r) => r.name === childRowName);
	if (!row) {
		frappe.msgprint(__("Wastage row not found on SPR."));
		return;
	}

	const esc = (s) => frappe.utils.escape_html(String(s ?? ""));
	const toNum = (v) => {
		const n = parseFloat(v);
		return Number.isFinite(n) ? n : 0;
	};

	const title =
		tableField === "custom_roll_waste" ? "ROLL WASTE" : tableField === "custom_running_patty_wastage" ? "PATTY WASTE" : "WASTE";

	const runDate = doc.run_date ? String(doc.run_date) : frappe.datetime.get_today();
	const quality = row.quality || "";
	const color = row.color || "";
	const gsm = row.gsm || "";
	const widthInch = row.width_inch ?? row.width ?? "";
	const meterPerRoll = row.meter_per_roll ?? row.meter_roll ?? "";
	const noOfShafts = row.no_of_shafts ?? row.shafts ?? "";
	const netWeight = row.wastage ?? row.net_wastage ?? row.wastage_qty ?? row.net_weight ?? "";
	const netWeightKg = toNum(netWeight);
	const batchNo = row.batch_no || row.source_roll || "";

	const barcodeText = String(batchNo || "").trim();
	const html = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>${esc(title)}</title>
    <style>
      @media print { .btn-panel { display:none !important; } @page { size: 4in 4in; margin:0; } }
      body { font-family: Arial, sans-serif; margin:0; padding:0; text-align:center; background:#eee; }
      .sticker { width:4in; height:4in; margin:16px auto; border:2px solid #000; background:#fff; box-sizing:border-box; }
      .inner { border:1px solid #000; margin:8px; padding:8px; height: calc(100% - 16px); display:flex; flex-direction:column; justify-content:space-between; }
      .hdr { font-size:26px; font-weight:900; color:#c1121f; border-bottom:2px solid #000; padding-bottom:6px; }
      table { width:100%; border-collapse:collapse; font-size:13px; text-align:left; }
      td { padding:4px 6px; }
      td.lbl { width:42%; font-weight:700; }
      td.val { font-weight:700; }
      .foot { display:flex; flex-direction:column; align-items:center; gap:6px; }
      #barcode { width: 100%; }
      .btn-panel { padding:10px; background:#eee; margin-top:8px; }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.0/dist/JsBarcode.all.min.js"></script>
  </head>
  <body>
    <div class="sticker">
      <div class="inner">
        <div>
          <div class="hdr">${esc(title)}</div>
          <table>
            <tr><td class="lbl">Date</td><td class="val">: ${esc(runDate)}</td></tr>
            <tr><td class="lbl">Quality</td><td class="val">: ${esc(quality)}</td></tr>
            <tr><td class="lbl">Color</td><td class="val">: ${esc(color)}</td></tr>
            <tr><td class="lbl">GSM</td><td class="val">: ${esc(gsm)}</td></tr>
            <tr><td class="lbl">Width</td><td class="val">: ${esc(widthInch)} Inches</td></tr>
            ${meterPerRoll ? `<tr><td class="lbl">Meter / Roll</td><td class="val">: ${esc(meterPerRoll)}</td></tr>` : ``}
            ${noOfShafts ? `<tr><td class="lbl">No of Shafts</td><td class="val">: ${esc(noOfShafts)}</td></tr>` : ``}
            <tr><td class="lbl">Net Weight</td><td class="val">: ${esc(netWeightKg.toFixed(2))} Kg</td></tr>
            ${barcodeText ? `<tr><td class="lbl">Batch No</td><td class="val">: ${esc(barcodeText)}</td></tr>` : ``}
          </table>
        </div>
        <div class="foot">
          ${barcodeText ? `<svg id="barcode"></svg>` : `<div style="height:20px;"></div>`}
        </div>
      </div>
    </div>
    <div class="btn-panel">
      <button onclick="window.print()" style="padding:10px 20px;font-weight:bold;cursor:pointer;">PRINT</button>
      <button onclick="window.close()" style="padding:10px 20px; margin-left:10px; font-weight:bold; cursor:pointer;">CLOSE</button>
    </div>
    <script>
      (function(){
        const text = ${JSON.stringify(barcodeText)};
        if (!text) return;
        try {
          JsBarcode("#barcode", text, {
            format: "CODE128",
            displayValue: true,
            fontSize: 12,
            textMargin: 0,
            height: 55,
            width: 2
          });
        } catch(e) {}
      })();
    </script>
  </body>
</html>`;

	const win = window.open("", "_blank", "height=650,width=500");
	if (!win) {
		frappe.msgprint(__("Popup blocked. Allow popups to print the label."));
		return;
	}
	win.document.write(html);
	win.document.close();
}

function cint(v) {
	const n = parseInt(v, 10);
	return Number.isFinite(n) ? n : 0;
}
