/** Shared Manual Job dialog for SPR form and GSM Production Entry. */

function _mjFlt(v) {
	return parseFloat(v) || 0;
}

function _mjCint(v) {
	const n = parseInt(v, 10);
	return Number.isFinite(n) ? n : 0;
}

function _mjWidthFromItemCode(itemCode) {
	const s = String(itemCode || "");
	const m = s.match(/(\d+(?:\.\d+)?)\s*["']?\s*$/);
	return m ? _mjFlt(m[1]) : 0;
}

function _mjWidthFromItemName(itemName) {
	const s = String(itemName || "");
	const m = s.match(/(\d+(?:\.\d+)?)\s*["']/);
	return m ? _mjFlt(m[1]) : 0;
}

/**
 * @param {{ sprName: string, onSuccess?: () => void }} opts
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
			if (!lines.length) {
				frappe.msgprint(__("No Production Plan lines found."));
				return;
			}
			const d = new frappe.ui.Dialog({
				title: __("Manual job"),
				size: "large",
				fields: [
					{
						fieldname: "hint",
						fieldtype: "HTML",
						options:
							'<div class="spr-manual-shell" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:10px 12px;margin-bottom:8px;">' +
							"<b>" +
							__("Manual Work Order Planner") +
							"</b>" +
							'<div class="text-muted small">' +
							__("Production Plan: {0}", [ppName || "—"]) +
							"</div></div>",
					},
					{
						fieldname: "no_of_shafts",
						fieldtype: "Int",
						label: __("Number of shafts"),
						reqd: 1,
						default: 1,
					},
					{
						fieldname: "no_of_rolls",
						fieldtype: "Int",
						label: __("Rolls per shaft"),
						reqd: 1,
						default: 1,
					},
					{
						fieldname: "combination_input",
						fieldtype: "Data",
						label: __("Combination widths (optional)"),
						description: __("Example: 34+34+42"),
					},
					{
						fieldname: "line_select_html",
						fieldtype: "HTML",
						options: '<div class="spr-manual-lines-wrap"></div>',
					},
				],
				primary_action_label: __("Create Work Order(s)"),
				primary_action() {
					const no_of_shafts = _mjCint(d.get_value("no_of_shafts"));
					const no_of_rolls = _mjCint(d.get_value("no_of_rolls"));
					if (no_of_shafts < 1 || no_of_rolls < 1) {
						frappe.msgprint(__("Shafts and rolls must be at least 1."));
						return;
					}
					const items = [];
					lines.forEach((line, idx) => {
						const cb = d.$wrapper.find('.spr-manual-inc[data-idx="' + idx + '"]');
						if (!cb.length || !cb.is(":checked")) {
							return;
						}
						const q = _mjFlt(d.$wrapper.find('.spr-manual-qty[data-idx="' + idx + '"]').val());
						const mr = _mjFlt(d.$wrapper.find('.spr-manual-meter-roll[data-idx="' + idx + '"]').val());
						if (!(q > 0) || !(mr > 0)) {
							frappe.msgprint(__("Enter valid WO qty and Meter/Roll for selected lines."));
							return;
						}
						const wInp = d.$wrapper.find('.spr-manual-width[data-idx="' + idx + '"]');
						let w = _mjFlt(wInp.val());
						if (!(w > 0)) {
							w =
								_mjWidthFromItemName(line.item_name) ||
								_mjFlt(line.width_inch) ||
								_mjWidthFromItemCode(line.item_code);
						}
						items.push({
							item_code: line.item_code,
							production_plan_item: line.production_plan_item,
							wo_qty: q,
							meter_roll: mr,
							width_inch: w,
							roll_count_per_shaft: no_of_rolls,
							selected_reuse_work_order:
								d.$wrapper.find('.spr-manual-reuse-wo[data-idx="' + idx + '"]').val() || "",
						});
					});
					if (!items.length) {
						frappe.msgprint(__("Select at least one line."));
						return;
					}
					d.hide();
					frappe.call({
						method:
							"production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_create_manual_jobs_multi",
						args: {
							shaft_production_run: sprName,
							no_of_shafts,
							no_of_rolls,
							items,
							combination_input: String(d.get_value("combination_input") || "").trim(),
						},
						freeze: true,
						callback(r2) {
							const m = r2.message || {};
							const wos = (m.work_orders || []).join(", ");
							frappe.show_alert({
								message: __("Work Order(s) {0} created (job {1}).", [wos, m.job_id || ""]),
								indicator: "green",
							});
							if (typeof opts.onSuccess === "function") {
								opts.onSuccess(m);
							}
						},
					});
				},
			});

			function defaultQty(line) {
				const nShafts = _mjCint(d.get_value("no_of_shafts")) || 1;
				const nRolls = _mjCint(d.get_value("no_of_rolls")) || 1;
				const net = _mjFlt(line.first_segment_planned_kg || line.net_per_shaft_kg);
				if (net > 0) {
					return Math.round(net * nShafts * nRolls * 1000) / 1000;
				}
				return _mjFlt(line.planned_qty);
			}

			function renderTable() {
				const wrap = d.$wrapper.find(".spr-manual-lines-wrap");
				let html =
					'<div style="overflow:auto;max-height:360px;border:1px solid #e2e8f0;border-radius:8px;">' +
					'<table class="table table-bordered table-condensed" style="font-size:12px;margin:0;">' +
					"<thead><tr><th></th><th>Item</th><th>Order</th><th>Width</th><th>GSM</th><th>Meter/Roll</th><th>WO qty</th><th>Reuse WO</th></tr></thead><tbody>";
				lines.forEach((line, idx) => {
					const w =
						_mjWidthFromItemName(line.item_name) ||
						_mjFlt(line.width_inch) ||
						_mjWidthFromItemCode(line.item_code);
					const reuseOpts = (line.reusable_work_orders || [])
						.map(
							(rw) =>
								'<option value="' +
								frappe.utils.escape_html(rw.name || "") +
								'">' +
								frappe.utils.escape_html(rw.name || "") +
								"</option>"
						)
						.join("");
					html +=
						"<tr><td><input type=\"checkbox\" class=\"spr-manual-inc\" data-idx=\"" +
						idx +
						'" checked /></td>' +
						"<td>" +
						frappe.utils.escape_html(line.item_code || "") +
						"</td>" +
						"<td>" +
						frappe.utils.escape_html(line.order_code || "") +
						"</td>" +
						'<td><input type="number" class="form-control input-xs spr-manual-width" data-idx="' +
						idx +
						'" value="' +
						w +
						'" step="0.01" style="width:70px;" /></td>' +
						"<td>" +
						frappe.utils.escape_html(String(line.gsm || "")) +
						"</td>" +
						'<td><input type="number" class="form-control input-xs spr-manual-meter-roll" data-idx="' +
						idx +
						'" value="800" step="0.01" style="width:80px;" /></td>' +
						'<td><input type="number" class="form-control input-xs spr-manual-qty" data-idx="' +
						idx +
						'" value="' +
						defaultQty(line) +
						'" step="0.001" style="width:90px;" /></td>' +
						'<td><select class="form-control input-xs spr-manual-reuse-wo" data-idx="' +
						idx +
						'" style="width:120px;"><option value=""></option>' +
						reuseOpts +
						"</select></td></tr>";
				});
				html += "</tbody></table></div>";
				wrap.html(html);
			}

			d.show();
			renderTable();
			d.fields_dict.no_of_shafts.$input.on("change", renderTable);
			d.fields_dict.no_of_rolls.$input.on("change", renderTable);
		},
	});
}
