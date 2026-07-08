/**
 * GSM Wastage + Recycle dialogs — mirror desk SPR child tables.
 */

import { gsmPrintWastageLabel } from "./spr_gsm_tools.js";

function _flt(v) {
	return typeof flt === "function" ? flt(v) : parseFloat(v) || 0;
}

function _esc(s) {
	return frappe.utils.escape_html(String(s ?? ""));
}

function _tableHtml(columns, rows, opts = {}) {
	const cols = columns && columns.length ? columns : Object.keys(rows[0] || {}).filter((k) => k !== "name");
	const showPrint = !!opts.showPrint;
	let head = cols.map((c) => {
		const label = typeof c === "string" ? c : c.label || c.fieldname;
		return `<th>${_esc(label)}</th>`;
	});
	if (showPrint) {
		head.push(`<th>${__("Print")}</th>`);
	}
	let body = "";
	if (!rows.length) {
		body = `<tr><td colspan="${cols.length + (showPrint ? 1 : 0)}" class="text-muted">${__(
			"No rows"
		)}</td></tr>`;
	} else {
		body = rows
			.map((row) => {
				const cells = cols
					.map((c) => {
						const fn = typeof c === "string" ? c : c.fieldname;
						return `<td>${_esc(row[fn] ?? "")}</td>`;
					})
					.join("");
				const printBtn = showPrint
					? `<td><button type="button" class="btn btn-xs btn-default gwm-print-btn" data-row="${_esc(
							row.name
					  )}">${__("Print Label")}</button></td>`
					: "";
				return `<tr data-row-name="${_esc(row.name)}">${cells}${printBtn}</tr>`;
			})
			.join("");
	}
	return `<table class="table table-bordered table-condensed gwm-grid"><thead><tr>${head.join(
		""
	)}</tr></thead><tbody>${body}</tbody></table>`;
}

function _stockPickerHtml(stock, selected = new Set()) {
	if (!stock.length) {
		return `<p class="text-muted">${__("No patty stock available.")}</p>`;
	}
	const head = `<tr>
		<th><input type="checkbox" class="gwm-select-all" /></th>
		<th>${__("Batch No")}</th>
		<th>${__("Quality")}</th>
		<th>${__("Color")}</th>
		<th>${__("GSM")}</th>
		<th>${__("Width")}</th>
		<th>${__("Available (Kg)")}</th>
	</tr>`;
	const body = stock
		.map((row, idx) => {
			const batch = row.batch_no || row.batch || "";
			const key = row.name || batch || String(idx);
			const checked = selected.has(key) ? "checked" : "";
			return `<tr data-stock-key="${_esc(key)}">
				<td><input type="checkbox" class="gwm-stock-cb" data-key="${_esc(key)}" ${checked} /></td>
				<td>${_esc(batch)}</td>
				<td>${_esc(row.quality || "")}</td>
				<td>${_esc(row.color || "")}</td>
				<td>${_esc(row.gsm ?? "")}</td>
				<td>${_esc(row.width_inch ?? row.width ?? "")}</td>
				<td>${_flt(row.available_kg ?? row.available ?? row.wastage).toFixed(3)}</td>
			</tr>`;
		})
		.join("");
	return `<table class="table table-bordered table-condensed gwm-stock-grid"><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

export function pickSessionSpr(sessionSprList) {
	const list = (sessionSprList || []).filter((s) => s && s.spr_name);
	if (!list.length) {
		frappe.msgprint(__("Create SPRs first."));
		return Promise.resolve(null);
	}
	if (list.length === 1) {
		return Promise.resolve(list[0]);
	}
	return new Promise((resolve) => {
		const options = list.map((s) => `${s.order_code || "—"} · ${s.spr_name}`).join("\n");
		const d = new frappe.ui.Dialog({
			title: __("Select Order / SPR"),
			fields: [
				{
					fieldname: "spr_pick",
					fieldtype: "Select",
					label: __("Order · SPR"),
					options,
					reqd: 1,
				},
			],
			primary_action_label: __("Continue"),
			primary_action() {
				const v = d.get_value("spr_pick");
				const idx = options.split("\n").indexOf(v);
				d.hide();
				resolve(idx >= 0 ? list[idx] : list[0]);
			},
		});
		d.show();
	});
}

async function _loadWastageContext(sprName) {
	const res = await frappe.call({
		method: "production_entry.production_planning.unified_production_entry_api.get_gsm_spr_wastage_context",
		args: { spr_name: sprName },
	});
	return res.message || {};
}

async function _loadPattyStock(sprName) {
	const res = await frappe.call({
		method: "production_entry.production_planning.unified_production_entry_api.get_gsm_available_patty_stock",
		args: { spr_name: sprName },
	});
	const msg = res.message || {};
	return msg.stock || msg.rows || msg.data || [];
}

function _rollsForSpr(rollLines, sprRow) {
	const ppId = sprRow.pp_id;
	return (rollLines || []).filter(
		(r) =>
			r.pp_id === ppId &&
			!r.is_wasted &&
			!r.is_bundle_row &&
			r.batch_no &&
			(r.row_locked || r.spr_item_name)
	);
}

export async function openGsmWastageDialog(opts = {}) {
	const sprRow = await pickSessionSpr(opts.sessionSprList);
	if (!sprRow) {
		return;
	}
	const sprName = sprRow.spr_name;

	const typeD = new frappe.ui.Dialog({
		title: __("Wastage") + ` · ${sprRow.order_code || ""} · ${sprName}`,
		fields: [
			{
				fieldname: "hint",
				fieldtype: "HTML",
				options: `<p>${__(
					"Choose wastage type. Running Patty Wastage is auto-filled on desk SPR when rolls are saved."
				)}</p>`,
			},
		],
		primary_action_label: __("Running Patty Wasteage"),
		primary_action() {
			typeD.hide();
			_openRunningPattyWastage(sprName, sprRow);
		},
		secondary_action_label: __("Roll Wasteage"),
		secondary_action() {
			typeD.hide();
			_openRollWastage(sprName, sprRow, opts);
		},
	});
	typeD.show();
}

async function _openRunningPattyWastage(sprName, sprRow) {
	const ctx = await _loadWastageContext(sprName);
	const table = (ctx.tables || {}).custom_running_patty_wastage || {};
	const rows = table.rows || [];
	const cols = table.columns || [];

	const d = new frappe.ui.Dialog({
		title: __("Running Patty Wasteage") + ` · ${sprRow.order_code || ""}`,
		size: "large",
		fields: [
			{
				fieldname: "grid_html",
				fieldtype: "HTML",
				options:
					rows.length > 0
						? _tableHtml(cols, rows, { showPrint: true })
						: `<p class="text-muted">${__(
								"No running patty wastage yet. Save roll entries first — desk SPR adds rows automatically."
						  )}</p>`,
			},
		],
		primary_action_label: __("Refresh"),
		primary_action() {
			d.hide();
			_openRunningPattyWastage(sprName, sprRow);
		},
	});
	d.show();
	d.$wrapper.on("click", ".gwm-print-btn", async function () {
		const rowName = $(this).data("row");
		await gsmPrintWastageLabel(sprName, rowName, "custom_running_patty_wastage");
	});
}

async function _openRollWastage(sprName, sprRow, opts) {
	const rolls = _rollsForSpr(opts.rollLines, sprRow);
	if (!rolls.length) {
		frappe.msgprint(__("No saved roll lines available to mark as waste."));
		return;
	}

	const rollHtml = `<table class="table table-bordered table-condensed">
		<thead><tr>
			<th><input type="checkbox" class="gwm-roll-all" /></th>
			<th>${__("Batch")}</th><th>${__("Job")}</th><th>${__("Quality")}</th>
			<th>${__("GSM")}</th><th>${__("Width")}</th><th>${__("Net Kg")}</th>
		</tr></thead>
		<tbody>${rolls
			.map(
				(r) => `<tr>
			<td><input type="checkbox" class="gwm-roll-cb" data-batch="${_esc(r.batch_no)}" data-row="${_esc(
					r.spr_item_name || ""
				)}" /></td>
			<td>${_esc(r.batch_no)}</td><td>${_esc(r.job_id || r.job || "")}</td>
			<td>${_esc(r.quality || "")}</td><td>${_esc(r.gsm || "")}</td>
			<td>${_esc(r.width_inch || "")}</td><td>${_flt(r.net_weight).toFixed(3)}</td>
		</tr>`
			)
			.join("")}</tbody></table>`;

	const d = new frappe.ui.Dialog({
		title: __("Roll Wasteage") + ` · ${sprRow.order_code || ""}`,
		size: "large",
		fields: [{ fieldname: "rolls_html", fieldtype: "HTML", options: rollHtml }],
		primary_action_label: __("Mark as Waste"),
		async primary_action() {
			const selected = [];
			d.$wrapper.find(".gwm-roll-cb:checked").each(function () {
				selected.push({
					batch_no: $(this).data("batch"),
					row_name: $(this).data("row"),
				});
			});
			if (!selected.length) {
				frappe.msgprint(__("Select at least one roll."));
				return;
			}
			d.get_primary_btn().prop("disabled", true);
			try {
				for (const sel of selected) {
					const roll = rolls.find(
						(r) => r.batch_no === sel.batch_no || r.spr_item_name === sel.row_name
					);
					await frappe.call({
						method:
							"production_entry.production_planning.unified_production_entry_api.mark_gsm_roll_waste",
						args: {
							spr_name: sprName,
							roll_payload: JSON.stringify(roll || sel),
							batch_no: sel.batch_no,
							row_name: sel.row_name,
						},
					});
					if (typeof opts.onRollWasted === "function") {
						opts.onRollWasted(roll || sel, sprRow);
					}
				}
				frappe.show_alert({ message: __("Roll(s) marked as waste"), indicator: "green" });
				d.hide();
				_showRollWasteGrid(sprName, sprRow);
			} catch (e) {
				frappe.msgprint(e.message || __("Failed to mark roll waste"));
			} finally {
				d.get_primary_btn().prop("disabled", false);
			}
		},
	});
	d.show();
	d.$wrapper.on("change", ".gwm-roll-all", function () {
		const on = $(this).prop("checked");
		d.$wrapper.find(".gwm-roll-cb").prop("checked", on);
	});
}

async function _showRollWasteGrid(sprName, sprRow) {
	const ctx = await _loadWastageContext(sprName);
	const table = (ctx.tables || {}).custom_roll_waste || {};
	const d = new frappe.ui.Dialog({
		title: __("Roll Waste") + ` · ${sprRow.order_code || ""}`,
		size: "large",
		fields: [
			{
				fieldname: "grid_html",
				fieldtype: "HTML",
				options: _tableHtml(table.columns || [], table.rows || [], { showPrint: true }),
			},
		],
		primary_action_label: __("Close"),
		primary_action() {
			d.hide();
		},
	});
	d.show();
	d.$wrapper.on("click", ".gwm-print-btn", async function () {
		const rowName = $(this).data("row");
		await gsmPrintWastageLabel(sprName, rowName, "custom_roll_waste");
	});
}

export async function openGsmRecycleDialog(opts = {}) {
	const sprRow = await pickSessionSpr(opts.sessionSprList);
	if (!sprRow) {
		return;
	}
	const sprName = sprRow.spr_name;
	await _openRecycleMain(sprName, sprRow, opts);
}

async function _openRecycleMain(sprName, sprRow, opts) {
	const ctx = await _loadWastageContext(sprName);
	const recycled = (ctx.tables || {}).custom_recycled_wastage_details || {};

	const d = new frappe.ui.Dialog({
		title: __("Recycle") + ` · ${sprRow.order_code || ""} · ${sprName}`,
		size: "extra-large",
		fields: [
			{
				fieldname: "actions_html",
				fieldtype: "HTML",
				options: `<div class="gwm-recycle-actions" style="margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap;">
					<button type="button" class="btn btn-default gwm-btn-patty">${__("View Patty Wastage")}</button>
					<button type="button" class="btn btn-default gwm-btn-roll-waste">${__("Roll Waste")}</button>
				</div>`,
			},
			{
				fieldname: "recycled_title",
				fieldtype: "HTML",
				options: `<h5 style="margin:8px 0;">${__("Recycled Wastage Details")}</h5>`,
			},
			{
				fieldname: "recycled_html",
				fieldtype: "HTML",
				options: _tableHtml(recycled.columns || [], recycled.rows || []),
			},
		],
		primary_action_label: __("Refresh"),
		primary_action() {
			d.hide();
			_openRecycleMain(sprName, sprRow, opts);
		},
	});
	d.show();

	d.$wrapper.on("click", ".gwm-btn-patty", () => {
		_openPattyStockPicker(sprName, sprRow, () => {
			d.hide();
			_openRecycleMain(sprName, sprRow, opts);
		});
	});
	d.$wrapper.on("click", ".gwm-btn-roll-waste", () => {
		_openRollWasteRecyclePicker(sprName, sprRow, () => {
			d.hide();
			_openRecycleMain(sprName, sprRow, opts);
		});
	});
}

async function _openPattyStockPicker(sprName, sprRow, onDone) {
	const stock = await _loadPattyStock(sprName);
	const selected = new Set();

	const d = new frappe.ui.Dialog({
		title: __("Available Patty Stock") + ` · ${sprRow.order_code || ""}`,
		size: "extra-large",
		fields: [{ fieldname: "stock_html", fieldtype: "HTML", options: _stockPickerHtml(stock, selected) }],
		primary_action_label: __("Consume Selected"),
		async primary_action() {
			const picks = [];
			d.$wrapper.find(".gwm-stock-cb:checked").each(function () {
				const key = $(this).data("key");
				const idx = stock.findIndex((r, i) => (r.name || r.batch_no || String(i)) === key);
				if (idx >= 0) {
					picks.push(stock[idx]);
				}
			});
			if (!picks.length) {
				frappe.msgprint(__("Select at least one row."));
				return;
			}
			d.get_primary_btn().prop("disabled", true);
			try {
				await frappe.call({
					method:
						"production_entry.production_planning.unified_production_entry_api.consume_gsm_recycled_wastage",
					args: {
						spr_name: sprName,
						patty_selections: JSON.stringify(picks),
					},
				});
				frappe.show_alert({ message: __("Added to Recycled Wastage Details"), indicator: "green" });
				d.hide();
				if (typeof onDone === "function") {
					onDone();
				}
			} catch (e) {
				frappe.msgprint(e.message || __("Consume failed"));
			} finally {
				d.get_primary_btn().prop("disabled", false);
			}
		},
	});
	d.show();
	d.$wrapper.on("change", ".gwm-select-all", function () {
		const on = $(this).prop("checked");
		d.$wrapper.find(".gwm-stock-cb").prop("checked", on);
	});
}

async function _openRollWasteRecyclePicker(sprName, sprRow, onDone) {
	const ctx = await _loadWastageContext(sprName);
	const table = (ctx.tables || {}).custom_roll_waste || {};
	const rows = table.rows || [];
	if (!rows.length) {
		frappe.msgprint(__("No roll waste rows on this SPR."));
		return;
	}

	const html = `<table class="table table-bordered table-condensed">
		<thead><tr>
			<th><input type="checkbox" class="gwm-rw-all" /></th>
			<th>${__("Batch")}</th><th>${__("Job")}</th><th>${__("Quality")}</th>
			<th>${__("GSM")}</th><th>${__("Width")}</th><th>${__("Wastage Kg")}</th>
		</tr></thead>
		<tbody>${rows
			.map(
				(r) => `<tr>
			<td><input type="checkbox" class="gwm-rw-cb" data-name="${_esc(r.name)}" /></td>
			<td>${_esc(r.batch_no || "")}</td><td>${_esc(r.job_id || "")}</td>
			<td>${_esc(r.quality || "")}</td><td>${_esc(r.gsm || "")}</td>
			<td>${_esc(r.width_inch || "")}</td><td>${_flt(r.wastage).toFixed(3)}</td>
		</tr>`
			)
			.join("")}</tbody></table>`;

	const d = new frappe.ui.Dialog({
		title: __("Roll Waste — Recycle") + ` · ${sprRow.order_code || ""}`,
		size: "large",
		fields: [{ fieldname: "rw_html", fieldtype: "HTML", options: html }],
		primary_action_label: __("Consume Selected"),
		async primary_action() {
			const names = [];
			d.$wrapper.find(".gwm-rw-cb:checked").each(function () {
				names.push($(this).data("name"));
			});
			if (!names.length) {
				frappe.msgprint(__("Select at least one row."));
				return;
			}
			d.get_primary_btn().prop("disabled", true);
			try {
				await frappe.call({
					method:
						"production_entry.production_planning.unified_production_entry_api.consume_gsm_recycled_wastage",
					args: {
						spr_name: sprName,
						roll_waste_row_names: JSON.stringify(names),
					},
				});
				frappe.show_alert({ message: __("Added to Recycled Wastage Details"), indicator: "green" });
				d.hide();
				if (typeof onDone === "function") {
					onDone();
				}
			} catch (e) {
				frappe.msgprint(e.message || __("Consume failed"));
			} finally {
				d.get_primary_btn().prop("disabled", false);
			}
		},
	});
	d.show();
	d.$wrapper.on("change", ".gwm-rw-all", function () {
		const on = $(this).prop("checked");
		d.$wrapper.find(".gwm-rw-cb").prop("checked", on);
	});
}
