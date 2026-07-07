/**
 * Manual Job dialog — same UI/logic as SPR Actions → Manual job.
 * Used by GSM Production Entry (Tools → Manual job). SPR keeps its own copy in shaft_production_run.js.
 */

function _mjFlt(v) {
	return typeof flt === "function" ? flt(v) : parseFloat(v) || 0;
}

function _mjCint(v) {
	return typeof cint === "function" ? cint(v) : (() => {
		const n = parseInt(v, 10);
		return Number.isFinite(n) ? n : 0;
	})();
}

function _mjWidthFromItemCode(itemCode) {
	const code = String(itemCode || "").trim();
	if (!/^\d+$/.test(code) || code.length < 16) {
		return 0;
	}
	const mm = parseInt(code.substring(12, 16), 10);
	if (isNaN(mm) || mm <= 0) {
		return 0;
	}
	return Math.round(Math.round((mm / 25.4) * 2) / 2 * 10) / 10;
}

function _mjWidthFromItemName(itemName) {
	const text = String(itemName || "");
	let m = text.match(/W\s*-\s*(\d+(?:\.\d+)?)/i);
	if (m) {
		return _mjFlt(m[1]);
	}
	m = text.match(/(\d+(?:\.\d+)?)\s*(?:''|"|″)/);
	if (m) {
		return _mjFlt(m[1]);
	}
	return 0;
}

function _mjManualDefaultWoQty(line, noShafts, noRolls) {
	const shafts = _mjCint(noShafts);
	const rolls = _mjCint(noRolls);
	const s = shafts > 0 ? shafts : 1;
	const r = rolls > 0 ? rolls : 1;
	const nps = line.net_per_shaft_kg != null ? _mjFlt(line.net_per_shaft_kg) : null;
	if (nps != null && nps > 0) {
		return nps * r * s;
	}
	const fs =
		line.first_segment_planned_kg != null && line.first_segment_planned_kg !== ""
			? _mjFlt(line.first_segment_planned_kg)
			: null;
	if (fs != null && fs > 0) {
		return fs * r * s;
	}
	const pq = _mjFlt(line.planned_qty);
	return pq > 0 ? pq : 1;
}

function _mjNormalizeWidthToken(token) {
	const raw = String(token || "")
		.replace(/inch|inches|in/gi, "")
		.replace(/["']/g, "")
		.trim();
	if (!raw) {
		return 0;
	}
	return _mjFlt(raw);
}

function _mjParseCombination(text) {
	return String(text || "")
		.split("+")
		.map((part) => _mjNormalizeWidthToken(part))
		.filter((w) => w > 0);
}

/**
 * @param {{ sprName: string, onSuccess?: (result?: object) => void }} opts
 */
export function openSprManualJobDialog(opts) {
	opts = opts || {};
	const sprName = opts.sprName;
	if (!sprName) {
		frappe.msgprint(__("Save or select a Shaft Production Run first."));
		return;
	}
	frappe.call({
		method:
			"production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_get_manual_job_catalog",
		args: { shaft_production_run: sprName },
		freeze: true,
		freeze_message: __("Loading Production Plan lines..."),
		callback(r) {
			const payload = r.message || {};
			const lines = payload.lines || [];
			const ppName = payload.production_plan || "";
			const sprUnit = payload.custom_unit || "";
			const maxShaftInches = _mjFlt(payload.max_shaft_inches || 0);
			if (!lines.length) {
				frappe.msgprint(
					__("No Production Plan lines found. Set Production Plan and ensure it has planned items.")
				);
				return;
			}
			const d = new frappe.ui.Dialog({
				title: __("Manual job"),
				fields: [
					{
						fieldname: "spr_manual_ui_style",
						fieldtype: "HTML",
						options:
							"<style>" +
							".spr-manual-shell{background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:12px 14px;margin-bottom:10px;}" +
							".spr-manual-shell b{font-weight:600;color:#0f172a;}" +
							".spr-manual-toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0 10px;}" +
							".spr-manual-summary{margin-left:auto;font-size:12px;color:#334155;background:#eef2ff;border:1px solid #c7d2fe;border-radius:999px;padding:4px 10px;}" +
							".spr-manual-table-wrap{overflow:auto;border:1px solid #dbe2ea;border-radius:12px;background:#fff;max-height:360px;}" +
							".spr-manual-table{font-size:12px;margin:0;min-width:1020px;table-layout:fixed;}" +
							".spr-manual-table thead th{position:sticky;top:0;background:#f1f5f9;z-index:1;border-bottom:1px solid #cbd5e1;color:#334155;}" +
							".spr-manual-table tbody tr:hover{background:#f8fafc;}" +
							".spr-manual-row-selected{background:#ecfeff !important;}" +
							".spr-manual-table input[type=number],.spr-manual-table select{height:28px;font-size:12px;}" +
							"</style>",
					},
					{
						fieldname: "spr_manual_pp_hint",
						fieldtype: "HTML",
						options:
							'<div class="spr-manual-shell">' +
							'<div style="display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;">' +
							"<div><b>" +
							__("Manual Work Order Planner") +
							'</b><div class="text-muted small">' +
							__("Choose shafts/roll logic, then confirm rows below.") +
							"</div></div>" +
							'<div class="text-muted small">' +
							__("Production Plan: {0}", [ppName || "—"]) +
							(sprUnit && maxShaftInches > 0
								? "<br>" +
								  __("Unit: {0} — max combination width {1}\"", [sprUnit, String(maxShaftInches)])
								: "") +
							"</div></div></div>",
					},
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
					{
						fieldname: "combination_gsm",
						fieldtype: "Int",
						label: __("Combination GSM"),
					},
					{
						fieldname: "combination_input",
						fieldtype: "Data",
						label: __("Combination widths (Inches)"),
						description: __("Example: 34+34+42. Same GSM only. Total rolls = segments × shafts."),
					},
					{
						fieldname: "combination_status_html",
						fieldtype: "HTML",
						options: '<div class="text-muted small spr-manual-combination-status"></div>',
					},
					{
						fieldname: "line_select_html",
						fieldtype: "HTML",
						label: __("Select items"),
						options:
							'<div class="spr-manual-toolbar">' +
							'<button type="button" class="btn btn-xs btn-default spr-manual-select-all">' +
							__("Select all") +
							"</button>" +
							'<button type="button" class="btn btn-xs btn-default spr-manual-select-none">' +
							__("Clear") +
							"</button>" +
							'<span class="spr-manual-summary spr-manual-selection-summary">—</span>' +
							"</div>" +
							'<div class="spr-manual-lines-wrap"></div>' +
							'<p class="text-muted small" style="margin-top:6px;">' +
							__("WO qty default = net/roll Kg x rolls x shafts") +
							"</p>",
					},
				],
				primary_action_label: __("Create Work Order(s)"),
				primary_action() {
					const no_of_shafts = _mjCint(d.get_value("no_of_shafts"));
					const no_of_rolls = _mjCint(d.get_value("no_of_rolls"));
					if (no_of_shafts < 1) {
						frappe.msgprint(__("Number of shafts must be at least 1."));
						return;
					}
					if (no_of_rolls < 1) {
						frappe.msgprint(__("Number of rolls per shaft must be at least 1."));
						return;
					}
					const items = [];
					const comboRaw = String(d.get_value("combination_input") || "").trim();
					const comboMode = !!comboRaw;
					lines.forEach((line, idx) => {
						const cb = d.$wrapper.find('.spr-manual-inc[data-idx="' + idx + '"]');
						if (!cb.length || !cb.is(":checked")) {
							return;
						}
						const q = _mjFlt(d.$wrapper.find('.spr-manual-qty[data-idx="' + idx + '"]').val());
						const mr = _mjFlt(d.$wrapper.find('.spr-manual-meter-roll[data-idx="' + idx + '"]').val());
						if (!(q > 0)) {
							frappe.msgprint(__("Enter valid Work Order qty for selected line."));
							return;
						}
						if (!(mr > 0)) {
							frappe.msgprint(__("Enter valid Meter/Roll for selected line."));
							return;
						}
						items.push({
							item_code: line.item_code,
							production_plan_item: line.production_plan_item,
							wo_qty: q,
							meter_roll: mr,
							width_inch: getManualLineWidth(idx),
							roll_count_per_shaft: comboMode
								? _mjCint(line.__combo_roll_count_per_shaft || 1)
								: _mjCint(d.get_value("no_of_rolls")) || 1,
							selected_reuse_work_order:
								d.$wrapper.find('.spr-manual-reuse-wo[data-idx="' + idx + '"]').val() || "",
						});
					});
					if (!items.length) {
						frappe.msgprint(__("Select at least one line with valid Meter/Roll and Work Order qty."));
						return;
					}
					const finalItems = [];
					if (comboMode) {
						const byItem = new Map();
						items.forEach((it) => {
							const key = [it.item_code || "", it.selected_reuse_work_order || ""].join("::");
							if (!byItem.has(key)) {
								byItem.set(key, {
									item_code: it.item_code,
									production_plan_item: it.production_plan_item,
									wo_qty: 0,
									meter_roll: it.meter_roll,
									width_inch: it.width_inch,
									roll_count_per_shaft: 0,
									selected_reuse_work_order: it.selected_reuse_work_order || "",
								});
							}
							const agg = byItem.get(key);
							agg.wo_qty += _mjFlt(it.wo_qty);
							agg.roll_count_per_shaft += _mjCint(it.roll_count_per_shaft || 1);
						});
						byItem.forEach((v) => {
							finalItems.push(v);
						});
					} else {
						finalItems.push(...items);
					}
					d.hide();
					frappe.call({
						method:
							"production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_create_manual_jobs_multi",
						args: {
							shaft_production_run: sprName,
							no_of_shafts,
							no_of_rolls: comboMode ? 1 : _mjCint(d.get_value("no_of_rolls")) || 1,
							items: finalItems,
							combination_input: comboRaw,
						},
						freeze: true,
						freeze_message: __("Creating / fetching Work Order(s)..."),
						callback(r2) {
							const m = r2.message || {};
							const wos = (m.work_orders || []).join(", ");
							const reused = (m.reused_work_orders || []).join(", ");
							const msg = reused
								? __("Work Order(s) {0} (job {1}). Reused unused manual WO(s): {2}.", [
										wos || "",
										m.job_id || "",
										reused,
								  ])
								: __("Work Order(s) {0} (job {1}).", [wos || "", m.job_id || ""]);
							frappe.show_alert({ message: msg, indicator: "green" });
							if (typeof opts.onSuccess === "function") {
								opts.onSuccess(m);
							}
						},
					});
				},
			});

			function getManualLineWidth(idx) {
				const inp = d.$wrapper.find('.spr-manual-width[data-idx="' + idx + '"]');
				if (inp.length) {
					const v = _mjFlt(inp.val());
					if (v > 0) {
						return v;
					}
				}
				const line = lines[idx];
				if (!line) {
					return 0;
				}
				const fromName = _mjWidthFromItemName(line.item_name);
				if (fromName > 0) {
					return fromName;
				}
				return _mjFlt(line.width_inch) || _mjWidthFromItemCode(line.item_code);
			}

			function renderManualLinesTable() {
				const nShafts = _mjCint(d.get_value("no_of_shafts"));
				const nRolls = _mjCint(d.get_value("no_of_rolls")) || 1;
				const wrap = d.$wrapper.find(".spr-manual-lines-wrap");
				if (!wrap.length) {
					return;
				}
				let html =
					'<div class="spr-manual-table-wrap">' +
					'<table class="table table-bordered table-condensed spr-manual-table">';
				html +=
					'<thead><tr><th style="width:36px;"></th><th>' +
					__("Item / PP row") +
					'</th><th style="width:110px;">' +
					__("Order Code") +
					'</th><th style="width:70px;">' +
					__("Width (Inches)") +
					'</th><th style="width:55px;">' +
					__("GSM") +
					'</th><th style="width:110px;">' +
					__("Meter/Roll") +
					'</th><th style="width:95px;">' +
					__("Net/roll (Kg)") +
					'</th><th style="width:190px;">' +
					__("Reuse WO") +
					'</th><th style="width:110px;">' +
					__("WO qty (Kg)") +
					"</th></tr></thead><tbody>";
				lines.forEach((line, idx) => {
					const wIn =
						_mjWidthFromItemName(line.item_name) ||
						_mjFlt(line.width_inch) ||
						_mjWidthFromItemCode(line.item_code);
					const nps =
						line.net_per_shaft_kg != null && line.net_per_shaft_kg !== ""
							? _mjFlt(line.net_per_shaft_kg)
							: null;
					const npsLabel =
						nps != null && nps > 0
							? nps.toFixed(2) +
							  (line.matched_job_id
								  ? " (" + __("job") + " " + String(line.matched_job_id) + ")"
								  : "")
							: "—";
					const defQ = _mjManualDefaultWoQty(line, nShafts, nRolls);
					const itemName = String(line.item_name || "").trim();
					const label =
						String(line.item_code || "") + (itemName ? " — " + itemName.substring(0, 40) : "");
					html += "<tr>";
					html +=
						'<td style="text-align:center;"><input type="checkbox" class="spr-manual-inc" data-idx="' +
						idx +
						'" checked /></td>';
					html +=
						'<td style="max-width:360px;white-space:normal;word-break:break-word;">' +
						frappe.utils.escape_html(label) +
						"</td>";
					html += "<td>" + frappe.utils.escape_html(line.order_code || "") + "</td>";
					html +=
						'<td><input type="number" class="input-with-feedback spr-manual-width" data-idx="' +
						idx +
						'" value="' +
						wIn.toFixed(1) +
						'" step="0.1" min="0" style="width:70px"/></td>';
					html +=
						"<td>" + (line.gsm != null && line.gsm !== "" ? _mjCint(line.gsm) : "—") + "</td>";
					html +=
						'<td><input type="number" class="input-with-feedback spr-manual-meter-roll" data-idx="' +
						idx +
						'" value="500" step="0.1" style="width:100px" placeholder="500"/></td>';
					html += "<td>" + frappe.utils.escape_html(npsLabel) + "</td>";
					const reuseWos = Array.isArray(line.reusable_work_orders) ? line.reusable_work_orders : [];
					let woSelect =
						'<select class="input-with-feedback spr-manual-reuse-wo" data-idx="' +
						idx +
						'" style="width:170px"><option value="">' +
						frappe.utils.escape_html(__("Auto (reuse latest unused)")) +
						'</option><option value="__NEW__">' +
						frappe.utils.escape_html(__("Create New WO")) +
						"</option>";
					reuseWos.forEach((wo) => {
						const woName = typeof wo === "string" ? wo : wo && (wo.name || wo.work_order || "");
						if (!woName) {
							return;
						}
						woSelect +=
							'<option value="' +
							frappe.utils.escape_html(String(woName)) +
							'">' +
							frappe.utils.escape_html(String(woName)) +
							"</option>";
					});
					woSelect += "</select>";
					html += '<td style="white-space:nowrap;">' + woSelect + "</td>";
					html +=
						'<td><input type="number" class="input-with-feedback spr-manual-qty" data-idx="' +
						idx +
						'" value="' +
						defQ.toFixed(2) +
						'" step="0.001" style="width:100px"/></td>';
					html += "</tr>";
				});
				html += "</tbody></table></div>";
				wrap.html(html);
				applyManualCombinationSelection();
				updateManualSelectionSummary();
			}

			function updateManualSelectionSummary() {
				const checked = d.$wrapper.find(".spr-manual-inc:checked");
				let totalQty = 0;
				d.$wrapper.find(".spr-manual-table tbody tr").removeClass("spr-manual-row-selected");
				checked.each(function () {
					const idx = _mjCint($(this).attr("data-idx"));
					const q = _mjFlt(d.$wrapper.find('.spr-manual-qty[data-idx="' + idx + '"]').val());
					totalQty += q > 0 ? q : 0;
					$(this).closest("tr").addClass("spr-manual-row-selected");
				});
				d.$wrapper.find(".spr-manual-selection-summary").text(
					__("Selected: {0} row(s) | WO Qty: {1} Kg", [checked.length, totalQty.toFixed(2)])
				);
			}

			function setManualCombinationStatus(message, colorClass) {
				const wrap = d.$wrapper.find(".spr-manual-combination-status");
				if (!wrap.length) {
					return;
				}
				const cls = colorClass || "text-muted";
				wrap.html(
					message ? '<span class="' + cls + '">' + frappe.utils.escape_html(message) + "</span>" : ""
				);
			}

			function recalcManualQtyInputs() {
				const nShafts = _mjCint(d.get_value("no_of_shafts")) || 1;
				const nRolls = _mjCint(d.get_value("no_of_rolls")) || 1;
				const comboRaw = String(d.get_value("combination_input") || "").trim();
				if (comboRaw) {
					applyManualCombinationSelection();
					return;
				}
				d.$wrapper.find(".spr-manual-inc:checked").each(function () {
					const idx = _mjCint($(this).attr("data-idx"));
					const line = lines[idx];
					if (!line) {
						return;
					}
					d.$wrapper
						.find('.spr-manual-qty[data-idx="' + idx + '"]')
						.val(_mjManualDefaultWoQty(line, nShafts, nRolls).toFixed(2));
				});
				updateManualSelectionSummary();
			}

			function applyManualCombinationSelection() {
				const comboRaw = String(d.get_value("combination_input") || "").trim();
				if (!comboRaw) {
					setManualCombinationStatus("");
					return;
				}
				const comboGsm = _mjCint(d.get_value("combination_gsm"));
				if (comboGsm < 1) {
					setManualCombinationStatus(__("Enter Combination GSM to auto-select widths."), "text-warning");
					return;
				}
				const widths = _mjParseCombination(comboRaw);
				if (!widths.length) {
					setManualCombinationStatus(__("Enter widths like 34+34+42."), "text-warning");
					return;
				}
				const totalWidth = widths.reduce((sum, w) => sum + _mjFlt(w), 0);
				if (maxShaftInches > 0 && totalWidth > maxShaftInches + 1e-6) {
					setManualCombinationStatus(
						__('{0} maximum shaft width is {1}". Combination {2} = {3}" is not allowed.', [
							sprUnit || __("Unit"),
							String(maxShaftInches),
							comboRaw,
							totalWidth.toFixed(1),
						]),
						"text-danger"
					);
					return;
				}
				const picks = [];
				const countsByIdx = {};
				for (let i = 0; i < widths.length; i++) {
					const targetWidth = _mjFlt(widths[i]);
					let matchIdx = -1;
					for (let j = 0; j < lines.length; j++) {
						const line = lines[j];
						if (_mjCint(line.gsm) !== comboGsm) {
							continue;
						}
						if (Math.abs(getManualLineWidth(j) - targetWidth) > 0.05) {
							continue;
						}
						matchIdx = j;
						break;
					}
					if (matchIdx === -1) {
						setManualCombinationStatus(
							__("No unused PP line found for GSM {0} width {1} Inches.", [comboGsm, targetWidth]),
							"text-danger"
						);
						return;
					}
					picks.push(matchIdx);
					countsByIdx[matchIdx] = (countsByIdx[matchIdx] || 0) + 1;
				}

				d.$wrapper.find(".spr-manual-inc").prop("checked", false);
				lines.forEach((line) => {
					delete line.__combo_roll_count_per_shaft;
				});
				Object.keys(countsByIdx).forEach((idxStr) => {
					const idx = _mjCint(idxStr);
					const rollCount = _mjCint(countsByIdx[idx] || 1);
					lines[idx].__combo_roll_count_per_shaft = rollCount;
					d.$wrapper.find('.spr-manual-inc[data-idx="' + idx + '"]').prop("checked", true);
					d.$wrapper
						.find('.spr-manual-qty[data-idx="' + idx + '"]')
						.val(
							_mjManualDefaultWoQty(
								lines[idx],
								_mjCint(d.get_value("no_of_shafts")) || 1,
								rollCount
							).toFixed(2)
						);
				});
				setManualCombinationStatus(
					__("Selected {0} segment(s) for GSM {1}: {2}", [
						picks.length,
						comboGsm,
						widths.join(" + "),
					]),
					"text-success"
				);
			}

			d.show();
			try {
				d.$wrapper.find(".modal-dialog").css("max-width", "1100px");
			} catch (e) {
				/* ignore */
			}
			renderManualLinesTable();
			d.$wrapper.on("click", ".spr-manual-select-all", function () {
				d.$wrapper.find(".spr-manual-inc").prop("checked", true);
				updateManualSelectionSummary();
			});
			d.$wrapper.on("click", ".spr-manual-select-none", function () {
				d.$wrapper.find(".spr-manual-inc").prop("checked", false);
				updateManualSelectionSummary();
			});
			d.$wrapper.on("change input", ".spr-manual-inc, .spr-manual-qty, .spr-manual-width", function () {
				updateManualSelectionSummary();
			});
			const ns = d.fields_dict.no_of_shafts;
			if (ns && ns.$input) {
				ns.$input.on("change input", recalcManualQtyInputs);
			}
			const nr = d.fields_dict.no_of_rolls;
			if (nr && nr.$input) {
				nr.$input.on("change input", recalcManualQtyInputs);
			}
			const cg = d.fields_dict.combination_gsm;
			if (cg && cg.$input) {
				cg.$input.on("change input", function () {
					if (String(d.get_value("combination_input") || "").trim()) {
						applyManualCombinationSelection();
					} else {
						renderManualLinesTable();
					}
				});
			}
			const ci = d.fields_dict.combination_input;
			if (ci && ci.$input) {
				ci.$input.on("change input", function () {
					if (String(d.get_value("combination_input") || "").trim()) {
						applyManualCombinationSelection();
					} else {
						renderManualLinesTable();
					}
				});
			}
		},
	});
}
