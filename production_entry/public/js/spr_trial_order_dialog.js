/**
 * Trail Order dialog — used by GSM Production Entry and desk SPR Tools.
 * Always creates a new Shaft Production Run (never writes into an existing production SPR).
 */
import "./spr_trial_smart_bom.js";

frappe.provide("production_entry.spr_trial_order");

function _trFlt(v) {
	return typeof flt === "function" ? flt(v) : parseFloat(v) || 0;
}

function _trCint(v) {
	return typeof cint === "function"
		? cint(v)
		: (() => {
				const n = parseInt(v, 10);
				return Number.isFinite(n) ? n : 0;
			})();
}

function _trParseCombination(text) {
	return String(text || "")
		.split("+")
		.map((part) => {
			const raw = String(part || "")
				.replace(/inch|inches|in/gi, "")
				.replace(/["']/g, "")
				.trim();
			return _trFlt(raw);
		})
		.filter((w) => w > 0);
}

function _trNetPerRollKg(gsm, widthInch, meterRoll) {
	const g = _trFlt(gsm);
	const w = _trFlt(widthInch);
	const m = _trFlt(meterRoll);
	if (!(g > 0 && w > 0 && m > 0)) {
		return 0;
	}
	return (g * w * m * 0.0254) / 1000;
}

function _trDefaultWoQty(line, nShafts, nRolls) {
	const mr = _trFlt(line.meter_roll) || 500;
	const net = _trNetPerRollKg(line.gsm, line.width_inch, mr);
	const s = _trCint(nShafts) > 0 ? _trCint(nShafts) : 1;
	const r = _trCint(nRolls) > 0 ? _trCint(nRolls) : 1;
	return net > 0 ? net * r * s : 1;
}

/**
 * @param {{
 *   unit?: string,
 *   runDate?: string,
 *   shift?: string,
 *   operator?: string,
 *   supervisor?: string,
 *   shaftProductionRun?: string,
 *   onSuccess?: (result?: object) => void,
 * }} opts
 */
export function openSprTrialOrderDialog(opts) {
	opts = opts || {};
	const unit = String(opts.unit || "").trim();
	if (!unit && !opts.shaftProductionRun) {
		frappe.msgprint(__("Unit is required to create a Trail Order."));
		return;
	}
	frappe.call({
		method:
			"production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_get_trial_order_context",
		args: {
			shaft_production_run: opts.shaftProductionRun || "",
			unit,
		},
		freeze: true,
		freeze_message: __("Loading Trail Order context..."),
		callback(r) {
			const ctx = r.message || {};
			showTrialOrderDialog(ctx, opts);
		},
	});
}

function showTrialOrderDialog(ctx, opts) {
	const trialLines = [];
	const trialBomCache = {};
	let activeTrialLineIdx = -1;
	let trialBomPreviewTimer = null;
	const sprUnit = ctx.custom_unit || opts.unit || "";
	const maxShaftInches = _trFlt(ctx.max_shaft_inches || 0);
	const whRm = ctx.source_warehouse || "";
	const whWip = ctx.wip_warehouse || "";
	const whFg = ctx.fg_warehouse || "";
	const whHint =
		whRm && whFg
			? "<br>" +
			  __("Warehouses: RM {0} → WIP {1} → FG {2}", [whRm, whWip || "—", whFg])
			: "";

	const d = new frappe.ui.Dialog({
		title: __("Trail Order"),
		fields: [
			{
				fieldname: "spr_trial_ui_style",
				fieldtype: "HTML",
				options:
					"<style>" +
					".spr-trial-shell{background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:12px 14px;margin-bottom:10px;}" +
					".spr-trial-table-wrap{overflow:auto;border:1px solid #dbe2ea;border-radius:12px;background:#fff;max-height:320px;}" +
					".spr-trial-table{font-size:12px;margin:0;min-width:980px;}" +
					".spr-trial-bom{margin-top:10px;padding:10px;border:1px dashed #cbd5e1;border-radius:8px;background:#fff;}" +
					".spr-trial-row-active{background:#ecfeff !important;}" +
					".spr-trial-bom-toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px;}" +
					".spr-trial-summary{font-size:12px;color:#334155;margin-left:auto;}" +
					"</style>",
			},
			{
				fieldname: "spr_trial_hint",
				fieldtype: "HTML",
				options:
					'<div class="spr-trial-shell"><b>' +
					__("Trail Order — fabric from Item Master") +
					'</b><div class="text-muted small">' +
					__("Creates a new Shaft Production Run with Work Order(s) and an Available Job.") +
					(sprUnit && maxShaftInches > 0
						? "<br>" + __("Unit: {0} — max combination width {1}\"", [sprUnit, String(maxShaftInches)])
						: sprUnit
							? "<br>" + __("Unit: {0}", [sprUnit])
							: "") +
					whHint +
					"</div></div>",
			},
			{ fieldname: "order_code", fieldtype: "Data", label: __("Order code"), reqd: 1 },
			{
				fieldname: "no_of_shafts",
				fieldtype: "Int",
				label: __("Number of shafts (deck positions)"),
				reqd: 1,
				default: 1,
			},
			{
				fieldname: "no_of_rolls",
				fieldtype: "Int",
				label: __("Number of rolls (per shaft)"),
				reqd: 1,
				default: 1,
			},
			{ fieldname: "quality", fieldtype: "Link", label: __("Quality"), options: "Quality Master" },
			{ fieldname: "color", fieldtype: "Link", label: __("Color"), options: "Colour Master" },
			{ fieldname: "gsm", fieldtype: "Int", label: __("GSM") },
			{ fieldname: "width_inch", fieldtype: "Float", label: __("Width (Inches)") },
			{
				fieldname: "combination_input",
				fieldtype: "Data",
				label: __("Combination widths (Inches)"),
				description: __("Optional: 34+34+42 for multi-width shaft."),
			},
			{
				fieldname: "add_line_html",
				fieldtype: "HTML",
				options:
					'<button type="button" class="btn btn-sm btn-primary spr-trial-add-line">' +
					__("Add / resolve line") +
					"</button>",
			},
			{
				fieldname: "lines_html",
				fieldtype: "HTML",
				label: __("Trial lines"),
				options: '<div class="spr-trial-lines-wrap"></div>',
			},
			{
				fieldname: "bom_preview_html",
				fieldtype: "HTML",
				label: __("BOM preview"),
				options:
					'<div class="spr-trial-bom-wrap text-muted small">' +
					__("Add a line to preview BOM.") +
					"</div>",
			},
			{
				fieldname: "trial_selection_summary",
				fieldtype: "HTML",
				options: '<div class="spr-trial-summary spr-trial-selection-summary text-muted small">—</div>',
			},
		],
		primary_action_label: __("Create Trail SPR"),
		primary_action() {
			const orderCode = String(d.get_value("order_code") || "").trim();
			if (!orderCode) {
				frappe.msgprint(__("Order code is required."));
				return;
			}
			const noShafts = _trCint(d.get_value("no_of_shafts"));
			const noRolls = _trCint(d.get_value("no_of_rolls"));
			if (noShafts < 1 || noRolls < 1) {
				frappe.msgprint(__("Shafts and rolls per shaft must be at least 1."));
				return;
			}
			const comboRaw = String(d.get_value("combination_input") || "").trim();
			if (comboRaw && maxShaftInches > 0) {
				const widths = _trParseCombination(comboRaw);
				const totalW = widths.reduce((s, w) => s + _trFlt(w), 0);
				if (totalW > maxShaftInches + 1e-6) {
					frappe.msgprint(
						__("Combination width {0}\" exceeds unit limit {1}\".", [
							totalW.toFixed(1),
							maxShaftInches,
						])
					);
					return;
				}
			}
			const selected = trialLines.filter((ln) => _trCint(ln.included) !== 0);
			if (!selected.length) {
				frappe.msgprint(__("Add and select at least one trial line."));
				return;
			}
			const items = [];
			for (let i = 0; i < selected.length; i++) {
				const ln = selected[i];
				const q = _trFlt(ln.wo_qty);
				const mr = _trFlt(ln.meter_roll);
				if (!(q > 0) || !(mr > 0)) {
					frappe.msgprint(__("Enter valid Meter/Roll and WO qty for each selected line."));
					return;
				}
				items.push({
					item_code: ln.item_code,
					wo_qty: q,
					meter_roll: mr,
					selected_reuse_work_order: ln.reuse_wo || "",
				});
			}
			d.hide();
			frappe.call({
				method:
					"production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_create_trial_jobs_multi",
				args: {
					shaft_production_run: opts.shaftProductionRun || "",
					create_new_spr: 1,
					order_code: orderCode,
					no_of_shafts: noShafts,
					no_of_rolls: noRolls,
					items,
					combination_input: comboRaw,
					unit: sprUnit || opts.unit || "",
					run_date: opts.runDate || "",
					shift: opts.shift || "",
					operator: opts.operator || "",
					supervisor: opts.supervisor || "",
				},
				freeze: true,
				freeze_message: __("Creating trial Shaft Production Run..."),
				callback(r2) {
					const m = r2.message || {};
					frappe.show_alert({
						message: __("Trail SPR {0} — job {1} — WO(s): {2}", [
							m.shaft_production_run || "",
							m.job_id || "",
							(m.work_orders || []).join(", "),
						]),
						indicator: "green",
					});
					if (typeof opts.onSuccess === "function") {
						opts.onSuccess(m);
					}
				},
			});
		},
	});

	function getActiveTrialLine() {
		if (activeTrialLineIdx >= 0 && activeTrialLineIdx < trialLines.length) {
			return trialLines[activeTrialLineIdx];
		}
		return null;
	}

	function updateTrialSelectionSummary() {
		const checked = trialLines.filter((ln) => _trCint(ln.included) !== 0);
		let totalQty = 0;
		checked.forEach((ln) => {
			totalQty += _trFlt(ln.wo_qty) > 0 ? _trFlt(ln.wo_qty) : 0;
		});
		d.$wrapper
			.find(".spr-trial-selection-summary")
			.text(__("Selected: {0} | WO Qty: {1} Kg", [checked.length, totalQty.toFixed(2)]));
	}

	function recalcTrialQtyInputs() {
		const nShafts = _trCint(d.get_value("no_of_shafts")) || 1;
		const nRolls = _trCint(d.get_value("no_of_rolls")) || 1;
		trialLines.forEach((ln, idx) => {
			if (_trCint(ln.included) === 0) {
				return;
			}
			const qty = _trDefaultWoQty(ln, nShafts, nRolls);
			ln.wo_qty = qty;
			const $inp = d.$wrapper.find('.spr-trial-qty[data-idx="' + idx + '"]');
			if ($inp.length) {
				$inp.val(qty.toFixed(2));
			}
		});
		updateTrialSelectionSummary();
		scheduleTrialBomPreviewRefresh();
	}

	function cacheTrialBomPayload(itemCode, payload) {
		if (!itemCode || !payload) {
			return;
		}
		trialBomCache[itemCode] = {
			bom: payload.bom || "",
			lines: payload.lines || [],
			ldr_percent: _trFlt(payload.ldr_percent),
		};
		const ln = trialLines.find((l) => l.item_code === itemCode);
		if (ln) {
			ln.bom = payload.bom || ln.bom;
		}
	}

	function fetchTrialBomForLine(ln, callback) {
		if (!ln || !ln.item_code) {
			return;
		}
		if (trialBomCache[ln.item_code]) {
			if (typeof callback === "function") {
				callback(trialBomCache[ln.item_code]);
			}
			return;
		}
		frappe.call({
			method:
				"production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_preview_trial_fabric_bom",
			args: {
				item_code: ln.item_code,
				company: ctx.company,
				quality: ln.quality,
				color: ln.color,
				gsm: ln.gsm,
			},
			callback(br) {
				const payload = br.message || {};
				cacheTrialBomPayload(ln.item_code, payload);
				if (typeof callback === "function") {
					callback(trialBomCache[ln.item_code]);
				}
			},
		});
	}

	function renderTrialBomPreview() {
		const ln = getActiveTrialLine();
		const wrap = d.$wrapper.find(".spr-trial-bom-wrap");
		if (!wrap.length) {
			return;
		}
		if (!ln || !ln.item_code) {
			wrap.html('<span class="text-muted">' + __("Add a line to preview BOM.") + "</span>");
			return;
		}
		const scaleQty =
			_trFlt(ln.wo_qty) > 0
				? _trFlt(ln.wo_qty)
				: _trDefaultWoQty(ln, d.get_value("no_of_shafts"), d.get_value("no_of_rolls"));
		const cached = trialBomCache[ln.item_code];

		function drawPreview(payload) {
			const lines = (payload && payload.lines) || [];
			const ldr = payload ? _trFlt(payload.ldr_percent) : 0;
			const bomName = payload ? payload.bom : "";
			let html = '<div class="spr-trial-bom">';
			html += '<div class="spr-trial-bom-toolbar">';
			html += "<b>" + __("BOM preview") + "</b>";
			if (bomName) {
				html += ' <span class="text-muted">(' + frappe.utils.escape_html(bomName) + ")</span>";
			}
			html +=
				'<button type="button" class="btn btn-xs btn-default spr-trial-edit-bom">' +
				__("Edit BOM / Set Recipe") +
				"</button>";
			html +=
				'<span class="spr-trial-summary">' +
				__("WO qty: {0} Kg", [scaleQty.toFixed(2)]) +
				(ldr ? " | LDR: " + ldr.toFixed(2) + "%" : "") +
				"</span></div>";
			html += '<table class="table table-condensed table-bordered" style="margin-top:6px;font-size:11px;">';
			html +=
				"<thead><tr><th>" +
				__("Item") +
				"</th><th>" +
				__("Qty") +
				"</th><th>" +
				__("UOM") +
				"</th></tr></thead><tbody>";
			lines.forEach((row) => {
				html +=
					"<tr><td>" +
					frappe.utils.escape_html(row.item_code || "") +
					"</td><td>" +
					(_trFlt(row.qty) * scaleQty).toFixed(5) +
					"</td><td>" +
					frappe.utils.escape_html(row.uom || "Kg") +
					"</td></tr>";
			});
			html += "</tbody></table></div>";
			wrap.html(html);
		}

		if (cached) {
			drawPreview(cached);
		} else {
			wrap.html('<span class="text-muted">' + __("Loading BOM preview...") + "</span>");
			fetchTrialBomForLine(ln, drawPreview);
		}
	}

	function scheduleTrialBomPreviewRefresh() {
		if (trialBomPreviewTimer) {
			clearTimeout(trialBomPreviewTimer);
		}
		trialBomPreviewTimer = setTimeout(renderTrialBomPreview, 150);
	}

	function renderTrialLinesTable() {
		const nShafts = _trCint(d.get_value("no_of_shafts")) || 1;
		const nRolls = _trCint(d.get_value("no_of_rolls")) || 1;
		const wrap = d.$wrapper.find(".spr-trial-lines-wrap");
		if (!wrap.length) {
			return;
		}
		let html =
			'<div class="spr-trial-table-wrap"><table class="table table-bordered table-condensed spr-trial-table">';
		html +=
			"<thead><tr><th></th><th>" +
			__("Item") +
			"</th><th>" +
			__("GSM") +
			"</th><th>" +
			__("Width") +
			"</th><th>" +
			__("Meter/Roll") +
			"</th><th>" +
			__("Net/roll") +
			"</th><th>" +
			__("Reuse WO") +
			"</th><th>" +
			__("WO qty") +
			"</th></tr></thead><tbody>";
		trialLines.forEach((ln, idx) => {
			const gsm = _trFlt(ln.gsm);
			const wIn = _trFlt(ln.width_inch);
			const mr = _trFlt(ln.meter_roll) || 500;
			ln.meter_roll = mr;
			const netKg = _trNetPerRollKg(gsm, wIn, mr);
			ln.net_per_roll_kg = netKg;
			if (_trCint(ln.included) !== 0) {
				ln.wo_qty = _trDefaultWoQty(ln, nShafts, nRolls);
			}
			let woSelect =
				'<select class="input-with-feedback spr-trial-reuse" data-idx="' +
				idx +
				'" style="width:150px"><option value="">' +
				__("Auto") +
				'</option><option value="__NEW__">' +
				__("Create New WO") +
				"</option>";
			(ln.reusable_work_orders || []).forEach((wo) => {
				const sel = ln.reuse_wo === wo ? " selected" : "";
				woSelect +=
					'<option value="' +
					frappe.utils.escape_html(String(wo)) +
					'"' +
					sel +
					">" +
					frappe.utils.escape_html(String(wo)) +
					"</option>";
			});
			woSelect += "</select>";
			const label =
				frappe.utils.escape_html(ln.item_code || "") +
				(ln.item_name ? " — " + frappe.utils.escape_html(String(ln.item_name).substring(0, 36)) : "");
			const rowCls = idx === activeTrialLineIdx ? " spr-trial-row-active" : "";
			html += '<tr class="spr-trial-line-row' + rowCls + '" data-idx="' + idx + '">';
			html +=
				'<td><input type="checkbox" class="spr-trial-inc" data-idx="' +
				idx +
				'" ' +
				(_trCint(ln.included) !== 0 ? "checked" : "") +
				"/></td>";
			html += "<td>" + label + "</td>";
			html += "<td>" + (ln.gsm != null ? _trCint(ln.gsm) : "") + "</td>";
			html += "<td>" + wIn.toFixed(1) + "</td>";
			html +=
				'<td><input type="number" class="spr-trial-meter" data-idx="' +
				idx +
				'" value="' +
				mr +
				'" step="0.1" style="width:90px"/></td>';
			html +=
				'<td class="spr-trial-net" data-idx="' +
				idx +
				'">' +
				(netKg > 0 ? netKg.toFixed(2) : "—") +
				"</td>";
			html += "<td>" + woSelect + "</td>";
			html +=
				'<td><input type="number" class="spr-trial-qty" data-idx="' +
				idx +
				'" value="' +
				_trFlt(ln.wo_qty).toFixed(2) +
				'" step="0.001" style="width:90px"/></td>';
			html += "</tr>";
		});
		html += "</tbody></table></div>";
		wrap.html(html);
		updateTrialSelectionSummary();
	}

	d.show();
	try {
		d.$wrapper.find(".modal-dialog").css("max-width", "1100px");
	} catch (e) {}

	d.$wrapper.on("click", ".spr-trial-add-line", function () {
		const quality = d.get_value("quality");
		const color = d.get_value("color");
		const gsm = _trCint(d.get_value("gsm"));
		const widthInch = _trFlt(d.get_value("width_inch"));
		if (!quality || !color || gsm < 1 || !(widthInch > 0)) {
			frappe.msgprint(__("Enter Quality, Color, GSM, and Width before adding a line."));
			return;
		}
		frappe.call({
			method:
				"production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_resolve_trial_fabric_item",
			args: {
				quality,
				color,
				gsm,
				width_inch: widthInch,
				company: ctx.company,
				create_if_missing: 1,
			},
			freeze: true,
			freeze_message: __("Resolving item and BOM..."),
			callback(rr) {
				const res = rr.message || {};
				if (!res.item_code) {
					frappe.msgprint(__("Could not resolve fabric item."));
					return;
				}
				frappe.db
					.get_list("Work Order", {
						filters: {
							production_item: res.item_code,
							docstatus: ["<", 2],
							status: ["not in", ["Completed", "Stopped", "Cancelled"]],
						},
						fields: ["name", "production_plan"],
						limit: 20,
						order_by: "modified desc",
					})
					.then((wos) => {
						const reusable = (wos || [])
							.filter((w) => !w.production_plan)
							.map((w) => w.name);
						trialLines.push({
							item_code: res.item_code,
							item_name: res.item_name,
							gsm: res.gsm || gsm,
							width_inch: res.width_inch || widthInch,
							quality,
							color,
							meter_roll: 500,
							wo_qty: 0,
							included: 1,
							reuse_wo: "",
							reusable_work_orders: reusable,
							bom: res.bom || "",
						});
						activeTrialLineIdx = trialLines.length - 1;
						renderTrialLinesTable();
						fetchTrialBomForLine(trialLines[activeTrialLineIdx], () => {
							renderTrialBomPreview();
						});
						frappe.show_alert({
							message: __("Line added: {0}", [res.item_code]),
							indicator: "green",
						});
					});
			},
		});
	});

	d.$wrapper.on("click", ".spr-trial-line-row", function (e) {
		if ($(e.target).is("input, select, option")) {
			return;
		}
		activeTrialLineIdx = _trCint($(this).attr("data-idx"));
		d.$wrapper.find(".spr-trial-line-row").removeClass("spr-trial-row-active");
		$(this).addClass("spr-trial-row-active");
		renderTrialBomPreview();
	});

	d.$wrapper.on("click", ".spr-trial-edit-bom", function () {
		const ln = getActiveTrialLine();
		if (!ln) {
			frappe.msgprint(__("Select a trial line first."));
			return;
		}
		if (!window.sprTrialFabricRecipe || typeof window.sprTrialFabricRecipe.openDialog !== "function") {
			frappe.msgprint(__("Recipe editor not loaded. Refresh the page."));
			return;
		}
		window.sprTrialFabricRecipe.openDialog(ctx, ln, (payload) => {
			cacheTrialBomPayload(ln.item_code, payload);
			if (payload && payload.bom) {
				ln.bom = payload.bom;
			}
			renderTrialBomPreview();
		});
	});

	d.$wrapper.on("change input", ".spr-trial-meter, .spr-trial-qty, .spr-trial-reuse, .spr-trial-inc", function () {
		const idx = _trCint($(this).attr("data-idx"));
		const ln = trialLines[idx];
		if (!ln) {
			return;
		}
		if ($(this).hasClass("spr-trial-meter")) {
			ln.meter_roll = _trFlt($(this).val());
			const netKg = _trNetPerRollKg(ln.gsm, ln.width_inch, ln.meter_roll);
			ln.net_per_roll_kg = netKg;
			d.$wrapper
				.find('.spr-trial-net[data-idx="' + idx + '"]')
				.text(netKg > 0 ? netKg.toFixed(2) : "—");
			if (_trCint(ln.included) !== 0) {
				const qty = _trDefaultWoQty(ln, d.get_value("no_of_shafts"), d.get_value("no_of_rolls"));
				ln.wo_qty = qty;
				d.$wrapper.find('.spr-trial-qty[data-idx="' + idx + '"]').val(qty.toFixed(2));
			}
			if (idx === activeTrialLineIdx) {
				scheduleTrialBomPreviewRefresh();
			}
		}
		if ($(this).hasClass("spr-trial-qty")) {
			ln.wo_qty = _trFlt($(this).val());
			if (idx === activeTrialLineIdx) {
				scheduleTrialBomPreviewRefresh();
			}
		}
		if ($(this).hasClass("spr-trial-reuse")) {
			ln.reuse_wo = $(this).val();
		}
		if ($(this).hasClass("spr-trial-inc")) {
			ln.included = $(this).is(":checked") ? 1 : 0;
			if (_trCint(ln.included) !== 0) {
				ln.wo_qty = _trDefaultWoQty(ln, d.get_value("no_of_shafts"), d.get_value("no_of_rolls"));
				d.$wrapper.find('.spr-trial-qty[data-idx="' + idx + '"]').val(_trFlt(ln.wo_qty).toFixed(2));
			}
		}
		updateTrialSelectionSummary();
	});

	["no_of_shafts", "no_of_rolls"].forEach((fn) => {
		const f = d.fields_dict[fn];
		if (f && f.$input) {
			f.$input.on("change input", recalcTrialQtyInputs);
		}
	});
}

production_entry.spr_trial_order.openDialog = openSprTrialOrderDialog;
