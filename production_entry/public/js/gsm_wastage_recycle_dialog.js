/**
 * GSM Wastage + Recycle dialogs — uses shared SPR patty stock + label modules.
 */

import { gsmPrintWastageLabel } from "./spr_gsm_tools.js";
import "./spr_patty_stock.js";

const GWM_STYLE_ID = "gsm-wastage-recycle-styles";

const DESK_STOCK_COLS = [
	{ key: "batch_no", label: __("Batch No"), filter: true },
	{ key: "quality", label: __("Quality"), filter: true },
	{ key: "color", label: __("Color"), filter: true },
	{ key: "gsm", label: __("GSM"), filter: true, num: true },
	{ key: "width_inch", label: __("Width"), filter: true, num: true },
	{ key: "available_kg", label: __("Available (Kg)"), filter: false, num: true },
];

const DESK_RECYCLED_COLS = [
	{ field: "job_id", label: __("Job ID") },
	{ field: "quality", label: __("Quality") },
	{ field: "color", label: __("Color") },
	{ field: "gsm", label: __("GSM"), num: true },
	{ field: "width_inch", label: __("Width (Inch)"), num: true },
	{ field: "meter_per_roll", label: __("Meter / Roll"), num: true },
	{ field: "no_of_shafts", label: __("No of Shafts"), num: true },
	{ field: "wastage", label: __("Wastage"), num: true },
	{ field: "recycled_qty", label: __("Recycled Qty"), num: true },
	{ field: "recycled", label: __("Recycled"), num: true },
	{ field: "available_qty", label: __("Available Qty"), num: true },
];

const DESK_ROLL_WASTE_COLS = [
	{ field: "batch_no", label: __("Batch No") },
	{ field: "roll_number", label: __("Roll No"), num: true },
	{ field: "item_code", label: __("Item Code") },
	{ field: "item_name", label: __("Item Name") },
	{ field: "job_id", label: __("Job ID") },
	{ field: "quality", label: __("Quality") },
	{ field: "color", label: __("Color") },
	{ field: "gsm", label: __("GSM"), num: true },
	{ field: "width_inch", label: __("Width (Inch)"), num: true },
	{ field: "meter_per_roll", label: __("Meter / Roll"), num: true },
	{ field: "no_of_shafts", label: __("No of Shafts"), num: true },
	{ field: "wastage", label: __("Wastage"), num: true },
	{ field: "spr_item_name", label: __("SPR Item Row") },
	{ field: "source_roll", label: __("Source Roll") },
];

const DESK_PATTY_COLS = [
	{ field: "job_id", label: __("Job ID") },
	{ field: "quality", label: __("Quality") },
	{ field: "color", label: __("Color") },
	{ field: "gsm", label: __("GSM"), num: true },
	{ field: "width_inch", label: __("Width (Inch)"), num: true },
	{ field: "meter_per_roll", label: __("Meter / Roll"), num: true },
	{ field: "no_of_shafts", label: __("No of Shafts"), num: true },
	{ field: "wastage", label: __("Wastage Qty"), num: true },
	{ field: "net_wastage", label: __("Net Wastage (Kgs)"), num: true },
];

function _flt(v) {
	return typeof flt === "function" ? flt(v) : parseFloat(v) || 0;
}

function _esc(s) {
	return frappe.utils.escape_html(String(s ?? ""));
}

function _injectGwmStyles() {
	if (document.getElementById(GWM_STYLE_ID)) {
		return;
	}
	const style = document.createElement("style");
	style.id = GWM_STYLE_ID;
	style.textContent = `
.gwm-shell { font-family: inherit; color: #1e293b; }
.gwm-section-title {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 700;
  color: #334155;
  letter-spacing: 0.02em;
}
.gwm-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}
.gwm-actions .btn {
  border-radius: 8px;
  font-weight: 600;
  padding: 8px 14px;
}
.gwm-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
  padding: 14px 16px;
  margin-bottom: 12px;
}
.gwm-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  margin-top: 8px;
}
.gwm-data-card {
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid #cbd5e1;
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.05);
}
.gwm-data-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e2e8f0;
}
.gwm-data-card-head strong {
  font-size: 13px;
  color: #0f172a;
}
.gwm-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4338ca;
  border: 1px solid #c7d2fe;
}
.gwm-kv-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
}
.gwm-kv {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.gwm-kv span {
  font-size: 10px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.gwm-kv strong {
  font-size: 13px;
  color: #0f172a;
  word-break: break-word;
}
.gwm-kv.gwm-kv-wide { grid-column: 1 / -1; }
.gwm-card-foot {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #e2e8f0;
  display: flex;
  justify-content: flex-end;
}
.gwm-table-wrap {
  overflow: auto;
  max-height: min(52vh, 420px);
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  background: #fff;
}
.gwm-desk-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 12px;
  min-width: 720px;
}
.gwm-desk-table th,
.gwm-desk-table td {
  border-bottom: 1px solid #e2e8f0;
  border-right: 1px solid #f1f5f9;
  padding: 8px 10px;
  vertical-align: middle;
  text-align: left;
}
.gwm-desk-table th:last-child,
.gwm-desk-table td:last-child { border-right: none; }
.gwm-desk-table thead th {
  background: #f1f5f9;
  font-weight: 700;
  color: #334155;
  position: sticky;
  top: 0;
  z-index: 2;
}
.gwm-desk-table thead tr.gwm-filter-row th {
  top: 36px;
  background: #f8fafc;
  padding: 4px 6px;
  z-index: 1;
}
.gwm-desk-table tbody tr:hover { background: #f8fafc; }
.gwm-desk-table tbody tr.gwm-selected { background: #eef2ff; }
.gwm-desk-table .gwm-num { text-align: right; font-variant-numeric: tabular-nums; }
.gwm-desk-table .gwm-check { width: 36px; text-align: center; }
.gwm-desk-table th.gwm-print-col,
.gwm-desk-table td.gwm-print-col {
  width: 104px;
  min-width: 104px;
  max-width: 104px;
  text-align: center;
  white-space: nowrap;
  position: sticky;
  right: 0;
  background: #fff;
  box-shadow: -4px 0 8px rgba(15, 23, 42, 0.05);
  z-index: 1;
}
.gwm-desk-table thead th.gwm-print-col { background: #f1f5f9; z-index: 2; }
.gwm-print-btn {
  white-space: nowrap;
  max-width: 100%;
  padding: 4px 8px;
  font-size: 11px;
  border-radius: 6px !important;
  font-weight: 600 !important;
}
.gwm-filter-input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 4px 6px;
  font-size: 11px;
  background: #fff;
}
.gwm-empty {
  padding: 24px 16px;
  text-align: center;
  color: #64748b;
  font-size: 13px;
  border: 1px dashed #cbd5e1;
  border-radius: 10px;
  background: #f8fafc;
}
`;
	document.head.appendChild(style);
}

function _val(row, ...keys) {
	for (const k of keys) {
		const v = row?.[k];
		if (v !== undefined && v !== null && String(v).trim() !== "") {
			return v;
		}
	}
	return "";
}

function _fmtNum(v, decimals = 3) {
	const n = _flt(v);
	if (!n && n !== 0) {
		return "";
	}
	return n.toFixed(decimals);
}

function _apiColsToDesk(apiCols, fallbackCols) {
	if (!Array.isArray(apiCols) || !apiCols.length) {
		return fallbackCols;
	}
	const numericTypes = new Set(["Float", "Int", "Currency"]);
	return apiCols
		.filter((c) => c.fieldname && !["name", "parent", "parentfield", "parenttype", "idx", "docstatus"].includes(c.fieldname))
		.map((c) => ({
			field: c.fieldname,
			label: c.label || c.fieldname,
			num:
				numericTypes.has(c.fieldtype) ||
				/width|meter|wastage|recycled|available|shaft|gsm|qty|kg/i.test(c.fieldname),
		}));
}

function _cellValue(row, field) {
	const aliases = {
		batch_no: ["batch_no", "batch", "source_roll"],
		width_inch: ["width_inch", "width", "w"],
		width: ["width", "width_inch", "w"],
		meter_per_roll: ["meter_per_roll", "meter_roll", "meter", "produced_length_mtrs", "produced_length_mtr"],
		wastage: ["wastage", "wastage_qty", "wastage_qt", "available", "available_qty", "available_kg", "net_wastage"],
		net_wastage: ["net_wastage", "net_wastage_kg", "wastage_qty", "wastage", "available", "available_qty"],
		recycled: ["recycled_qty", "recycled", "recycled_kg", "available_qty", "available"],
		recycled_qty: ["recycled_qty", "recycled", "recycled_kg", "available_qty", "available"],
		available_qty: ["available_qty", "available", "available_kg", "wastage_qty", "wastage", "net_wastage"],
		available_kg: ["available_kg", "available", "available_qty", "wastage", "net_wastage"],
		roll_number: ["roll_number", "roll_no"],
	};
	return _val(row, ...(aliases[field] || [field]));
}

function _rollNoFromBatch(batchNo) {
	const bn = String(batchNo || "").trim();
	if (!bn || !bn.includes("/")) {
		return "";
	}
	const suffix = bn.split("/").pop();
	const n = parseInt(suffix, 10);
	return Number.isFinite(n) ? String(n) : "";
}

function _normalizePattyRow(row) {
	const normalized = {
		...row,
		batch_no: _val(row, "batch_no", "batch", "source_roll"),
		roll_number: _val(row, "roll_number", "roll_no") || _rollNoFromBatch(_val(row, "batch_no", "batch", "source_roll")),
		quality: _val(row, "quality"),
		color: _val(row, "color"),
		gsm: _val(row, "gsm"),
		width_inch: _val(row, "width_inch", "width", "w"),
		width: _val(row, "width", "width_inch", "w"),
		meter_per_roll: _val(row, "meter_per_roll", "meter_roll", "meter", "produced_length_mtrs", "produced_length_mtr"),
		no_of_shafts: _val(row, "no_of_shafts", "shafts", "no_of_shaft"),
		wastage: _val(row, "wastage", "wastage_qty", "wastage_qt", "available", "available_qty", "available_kg"),
		wastage_qty: _val(row, "wastage_qty", "wastage_qt", "wastage", "net_wastage"),
		net_wastage: _val(row, "net_wastage", "net_wastage_kg", "net_wastage_kgs", "wastage_qty", "wastage", "available", "available_qty"),
		recycled: _val(row, "recycled_qty", "recycled", "recycled_kg", "available_qty", "available"),
		recycled_qty: _val(row, "recycled_qty", "recycled", "recycled_kg", "available_qty", "available"),
		available: _val(row, "available", "available_qty", "available_kg", "wastage", "net_wastage"),
		available_kg: _val(row, "available_kg", "available", "available_qty", "wastage", "net_wastage"),
		spr_item_name: _val(row, "spr_item_name", "source_roll_waste_row"),
		source_roll: _val(row, "source_roll", "batch_no", "batch"),
	};
	return normalized;
}

function _deskTableHtml(cols, rows, opts = {}) {
	const showPrint = !!opts.showPrint;
	const tableClass = opts.tableClass || "gwm-desk-table";
	let head = cols
		.map((c) => {
			const cls = c.num ? "gwm-num" : "";
			return `<th class="${cls}">${_esc(c.label)}</th>`;
		})
		.join("");
	if (showPrint) {
		head += `<th class="gwm-print-col">${__("Print")}</th>`;
	}
	let body = "";
	if (!rows.length) {
		body = `<tr><td colspan="${cols.length + (showPrint ? 1 : 0)}" class="gwm-empty">${__(
			"No rows"
		)}</td></tr>`;
	} else {
		body = rows
			.map((raw) => {
				const row = _normalizePattyRow(raw);
				const cells = cols
					.map((c) => {
						let v = _cellValue(row, c.field);
						if (c.num) {
							v = _fmtNum(v, c.field === "gsm" || c.field === "no_of_shafts" ? 0 : 3);
						}
						const cls = c.num ? "gwm-num" : "";
						return `<td class="${cls}">${_esc(v)}</td>`;
					})
					.join("");
				const printBtn = showPrint
					? `<td class="gwm-print-col"><button type="button" class="btn btn-xs btn-default gwm-print-btn" data-row="${_esc(
							row.name
					  )}">${__("Print Label")}</button></td>`
					: "";
				return `<tr data-row-name="${_esc(row.name)}">${cells}${printBtn}</tr>`;
			})
			.join("");
	}
	return `<div class="gwm-table-wrap"><table class="${tableClass}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function _dataCardsHtml(rows, opts = {}) {
	const kind = opts.kind || "waste";
	if (!rows.length) {
		return `<div class="gwm-empty">${opts.emptyText || __("No rows")}</div>`;
	}
	const cards = rows
		.map((raw) => {
			const row = _normalizePattyRow(raw);
			const title =
				kind === "roll"
					? _val(row, "batch_no") || __("Roll Waste")
					: `${__("Job")} ${_val(row, "job_id") || "—"}`;
			const badge =
				kind === "roll"
					? __("Roll Waste")
					: row.net_wastage
						? `${_fmtNum(row.net_wastage)} Kg`
						: __("Patty Wastage");
			const printAttr = row.name ? `data-row="${_esc(row.name)}"` : "";
			return `<div class="gwm-data-card">
				<div class="gwm-data-card-head">
					<strong>${_esc(title)}</strong>
					<span class="gwm-badge">${_esc(badge)}</span>
				</div>
				<div class="gwm-kv-grid">
					<div class="gwm-kv"><span>${__("Quality")}</span><strong>${_esc(row.quality)}</strong></div>
					<div class="gwm-kv"><span>${__("Color")}</span><strong>${_esc(row.color)}</strong></div>
					<div class="gwm-kv"><span>${__("GSM")}</span><strong>${_esc(row.gsm)}</strong></div>
					<div class="gwm-kv"><span>${__("Width")}</span><strong>${_esc(row.width_inch)}</strong></div>
					<div class="gwm-kv"><span>${__("Meter / Roll")}</span><strong>${_esc(row.meter_per_roll)}</strong></div>
					<div class="gwm-kv"><span>${__("Shafts")}</span><strong>${_esc(row.no_of_shafts)}</strong></div>
					<div class="gwm-kv"><span>${__("Wastage Qty")}</span><strong>${_esc(_fmtNum(row.wastage))}</strong></div>
					<div class="gwm-kv"><span>${__("Net Wastage")}</span><strong>${_esc(_fmtNum(row.net_wastage || row.wastage))} Kg</strong></div>
					${row.recycled ? `<div class="gwm-kv"><span>${__("Recycled")}</span><strong>${_esc(_fmtNum(row.recycled))} Kg</strong></div>` : ""}
				</div>
				${
					opts.showPrint && row.name
						? `<div class="gwm-card-foot"><button type="button" class="btn btn-xs btn-default gwm-print-btn" ${printAttr}>${__(
								"Print Label"
						  )}</button></div>`
						: ""
				}
			</div>`;
		})
		.join("");
	return `<div class="gwm-card-grid">${cards}</div>`;
}

function _stockPickerHtml(stock) {
	_injectGwmStyles();
	if (!stock.length) {
		return `<div class="gwm-empty">${__("No patty stock available for this SPR.")}</div>`;
	}

	const headCells = DESK_STOCK_COLS.map(
		(c) => `<th class="${c.num ? "gwm-num" : ""}">${_esc(c.label)}</th>`
	).join("");
	const filterCells = DESK_STOCK_COLS.map((c, i) => {
		if (!c.filter) {
			return "<th></th>";
		}
		return `<th><input type="text" class="gwm-filter-input" data-filter-col="${i}" placeholder="${__(
			"Filter"
		)}" /></th>`;
	}).join("");

	const body = stock
		.map((raw, idx) => {
			const row = _normalizePattyRow(raw);
			const batch = row.batch_no || "";
			const key = row.name || batch || String(idx);
			const cells = DESK_STOCK_COLS.map((c) => {
				let v = row[c.key];
				if (c.key === "width_inch") {
					v = row.width_inch;
				}
				if (c.num) {
					v = c.key === "gsm" ? _fmtNum(v, 0) : _fmtNum(v, 3);
				}
				return `<td class="${c.num ? "gwm-num" : ""}">${_esc(v)}</td>`;
			}).join("");
			const searchParts = DESK_STOCK_COLS.map((c) => {
				if (c.key === "width_inch") {
					return String(row.width_inch || "");
				}
				if (c.key === "available_kg") {
					return String(row.available_kg || "");
				}
				return String(row[c.key] || "");
			});
			return `<tr class="gwm-stock-row" data-stock-key="${_esc(key)}" data-search="${_esc(
				searchParts.join("|")
			)}">
				<td class="gwm-check"><input type="checkbox" class="gwm-stock-cb" data-key="${_esc(key)}" /></td>
				${cells}
			</tr>`;
		})
		.join("");

	return `<div class="gwm-shell gwm-card">
		<div class="gwm-section-title">${__("Available Patty Stock")}</div>
		<div class="gwm-table-wrap gwm-desk-stock-wrap">
			<table class="gwm-desk-table gwm-desk-stock">
				<thead>
					<tr>
						<th class="gwm-check"><input type="checkbox" class="gwm-select-all" title="${__(
							"Select all"
						)}" /></th>
						${headCells}
					</tr>
					<tr class="gwm-filter-row">
						<th></th>
						${filterCells}
					</tr>
				</thead>
				<tbody>${body}</tbody>
			</table>
		</div>
	</div>`;
}

function _wireStockFilters($wrapper) {
	$wrapper.on("input", ".gwm-filter-input", function () {
		const filters = [];
		$wrapper.find(".gwm-filter-input").each(function () {
			filters.push({
				col: parseInt($(this).data("filter-col"), 10),
				val: String($(this).val() || "").trim().toLowerCase(),
			});
		});
		$wrapper.find(".gwm-stock-row").each(function () {
			const parts = String($(this).data("search") || "").split("|");
			let show = true;
			for (const f of filters) {
				if (!f.val && f.val !== "0") {
					continue;
				}
				const cell = String(parts[f.col] || "").toLowerCase();
				if (!cell.includes(f.val)) {
					show = false;
					break;
				}
			}
			$(this).toggle(show);
		});
	});
}

function _wireSelectAll($wrapper, rowCb, allCb) {
	$wrapper.on("change", allCb, function () {
		const on = $(this).prop("checked");
		$wrapper.find(rowCb).prop("checked", on);
	});
}

export function pickSessionSpr(sessionSprList, opts = {}) {
	_injectGwmStyles();
	const list = (sessionSprList || []).filter((s) => s && s.spr_name);
	if (!list.length) {
		frappe.msgprint(__("No SPR found for this shift."));
		return Promise.resolve(null);
	}
	const preferPpId = opts.pp_id || opts.ppId || "";
	if (preferPpId) {
		const preferred = list.find((s) => s.pp_id === preferPpId);
		if (preferred) {
			return Promise.resolve(preferred);
		}
	}
	const preferSpr = _cstr(opts.spr_name || opts.sprName);
	if (preferSpr) {
		const preferred = list.find((s) => s.spr_name === preferSpr);
		if (preferred) {
			return Promise.resolve(preferred);
		}
	}
	if (list.length === 1) {
		return Promise.resolve(list[0]);
	}
	return new Promise((resolve) => {
		const optionLines = list.map((s) => `${s.order_code || "—"} · ${s.spr_name}`);
		const options = optionLines.join("\n");
		let defaultIdx = 0;
		if (preferPpId) {
			const idx = list.findIndex((s) => s.pp_id === preferPpId);
			if (idx >= 0) {
				defaultIdx = idx;
			}
		} else if (preferSpr) {
			const idx = list.findIndex((s) => s.spr_name === preferSpr);
			if (idx >= 0) {
				defaultIdx = idx;
			}
		}
		const d = new frappe.ui.Dialog({
			title: __("Select Order / SPR"),
			fields: [
				{
					fieldname: "spr_pick",
					fieldtype: "Select",
					label: __("Order · SPR"),
					options,
					reqd: 1,
					default: optionLines[defaultIdx],
				},
			],
			primary_action_label: __("Continue"),
			primary_action() {
				const v = d.get_value("spr_pick");
				const idx = optionLines.indexOf(v);
				d.hide();
				resolve(idx >= 0 ? list[idx] : list[0]);
			},
		});
		d.show();
	});
}

function _cstr(v) {
	return String(v ?? "").trim();
}

async function _loadWastageContext(sprName) {
	const res = await frappe.call({
		method: "production_entry.production_planning.unified_production_entry_api.get_gsm_spr_wastage_context",
		args: { spr_name: sprName },
	});
	return res.message || {};
}

function _bestChildTable(ctx, preferredKey, matchRe, skipKeys = []) {
	const tables = ctx?.tables || {};
	const candidates = [];
	const direct = tables[preferredKey];
	if (direct) {
		candidates.push(direct);
	}
	for (const [key, table] of Object.entries(tables)) {
		if (!table || skipKeys.includes(key)) {
			continue;
		}
		if (matchRe.test(key) || matchRe.test(table.child_doctype || "")) {
			candidates.push(table);
		}
	}
	return candidates.reduce(
		(best, table) => ((table?.rows || []).length > (best?.rows || []).length ? table : best),
		direct || { rows: [], columns: [] }
	);
}

function _pattyWastageTable(ctx) {
	const tables = ctx?.tables || {};
	const direct = tables.custom_running_patty_wastage;
	if ((direct?.rows || []).length) {
		return direct;
	}
	return _bestChildTable(
		ctx,
		"custom_running_patty_wastage",
		/patty/i,
		["custom_roll_waste", "custom_recycled_wastage_details"]
	);
}

function _rollWasteTable(ctx) {
	return _bestChildTable(
		ctx,
		"custom_roll_waste",
		/roll.?waste|waste/i,
		["custom_running_patty_wastage", "custom_recycled_wastage_details"]
	);
}

function _rowDataFromPrintBtn($btn, rows) {
	const rowName = String($btn.attr("data-row") || "").trim();
	if (!rowName) {
		return null;
	}
	return (rows || []).find((r) => r && r.name === rowName) || null;
}

async function _bindWastagePrint($wrapper, sprName, tableField, rows) {
	$wrapper.off("click.gwmPrint").on("click.gwmPrint", ".gwm-print-btn", async function () {
		const $btn = $(this);
		const rowData = _rowDataFromPrintBtn($btn, rows);
		await gsmPrintWastageLabel(
			sprName,
			String($btn.attr("data-row") || "").trim(),
			tableField,
			rowData
		);
	});
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
	_injectGwmStyles();
	const sprRow = await pickSessionSpr(opts.sessionSprList, opts);
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
				options: `<div class="gwm-shell"><p>${__(
					"Choose wastage type. Running Patty Wastage is auto-filled on desk SPR when rolls are saved."
				)}</p></div>`,
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
	const table = _pattyWastageTable(ctx);
	const rows = (table.rows || []).map(_normalizePattyRow);
	const pattyCols = _apiColsToDesk(table.columns, DESK_PATTY_COLS);

	const content =
		rows.length > 0
			? `<div class="gwm-shell">
				<div class="gwm-card">
					<div class="gwm-section-title">${__("Running Patty Wastage")}</div>
					${_dataCardsHtml(rows, { kind: "patty", showPrint: true })}
				</div>
				<div class="gwm-card" style="margin-top:12px;">
					<div class="gwm-section-title">${__("Table View")}</div>
					${_deskTableHtml(pattyCols, rows, { showPrint: true })}
				</div>
			</div>`
			: `<div class="gwm-empty">${__(
					"No running patty wastage yet. Save roll entries first — desk SPR adds rows automatically. If wastage shows on the SPR form, save that SPR on desk first."
			  )}</div>`;

	const d = new frappe.ui.Dialog({
		title: __("Running Patty Wasteage") + ` · ${sprRow.order_code || ""}`,
		size: "extra-large",
		fields: [{ fieldname: "grid_html", fieldtype: "HTML", options: content }],
		primary_action_label: __("Refresh"),
		primary_action() {
			d.hide();
			_openRunningPattyWastage(sprName, sprRow);
		},
	});
	d.show();
	_bindWastagePrint(d.$wrapper, sprName, table.resolved_fieldname || "custom_running_patty_wastage", rows);
}

async function _openRollWastage(sprName, sprRow, opts) {
	const ctx = await _loadWastageContext(sprName);
	const wasteTable = _rollWasteTable(ctx);
	const wasteRows = (wasteTable.rows || []).map(_normalizePattyRow);
	const rollWasteCols = _apiColsToDesk(wasteTable.columns, DESK_ROLL_WASTE_COLS);
	const rolls = _rollsForSpr(opts.rollLines, sprRow);
	const selectRollHtml = rolls.length
		? `<div class="gwm-card">
			<div class="gwm-section-title">${__("Select rolls to mark as waste")}</div>
			<div class="gwm-table-wrap">
				<table class="gwm-desk-table">
					<thead><tr>
						<th class="gwm-check"><input type="checkbox" class="gwm-roll-all" /></th>
						<th>${__("Batch")}</th><th>${__("Job")}</th><th>${__("Quality")}</th>
						<th>${__("GSM")}</th><th class="gwm-num">${__("Width")}</th><th class="gwm-num">${__("Net Kg")}</th>
					</tr></thead>
					<tbody>${rolls
						.map(
							(r) => `<tr>
						<td class="gwm-check"><input type="checkbox" class="gwm-roll-cb" data-batch="${_esc(
							r.batch_no
						)}" data-row="${_esc(r.spr_item_name || "")}" /></td>
						<td>${_esc(r.batch_no)}</td><td>${_esc(r.job_id || r.job || "")}</td>
						<td>${_esc(r.quality || "")}</td><td>${_esc(r.gsm || "")}</td>
						<td class="gwm-num">${_esc(r.width_inch || "")}</td><td class="gwm-num">${_flt(r.net_weight).toFixed(3)}</td>
					</tr>`
						)
						.join("")}</tbody>
				</table>
			</div>
		</div>`
		: `<div class="gwm-card"><div class="gwm-empty">${__(
				"No active saved roll lines available to mark as waste."
		  )}</div></div>`;
	const existingWasteHtml = `<div class="gwm-card" style="margin-top:12px;">
		<div class="gwm-section-title">${__("Already Marked Roll Waste")}</div>
		${_dataCardsHtml(wasteRows, { kind: "roll", showPrint: true })}
	</div>
	<div class="gwm-card" style="margin-top:12px;">
		<div class="gwm-section-title">${__("Roll Waste Table")}</div>
		${_deskTableHtml(rollWasteCols, wasteRows, { showPrint: true })}
	</div>`;
	const rollHtml = `<div class="gwm-shell">${selectRollHtml}${existingWasteHtml}</div>`;

	const d = new frappe.ui.Dialog({
		title: __("Roll Wasteage") + ` · ${sprRow.order_code || ""}`,
		size: "extra-large",
		fields: [{ fieldname: "rolls_html", fieldtype: "HTML", options: rollHtml }],
		primary_action_label: rolls.length ? __("Mark as Waste") : __("Refresh"),
		async primary_action() {
			if (!rolls.length) {
				d.hide();
				_openRollWastage(sprName, sprRow, opts);
				return;
			}
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
				_openRollWastage(sprName, sprRow, opts);
			} catch (e) {
				frappe.msgprint(e.message || __("Failed to mark roll waste"));
			} finally {
				d.get_primary_btn().prop("disabled", false);
			}
		},
	});
	d.show();
	_wireSelectAll(d.$wrapper, ".gwm-roll-cb", ".gwm-roll-all");
	_bindWastagePrint(d.$wrapper, sprName, wasteTable.resolved_fieldname || "custom_roll_waste", wasteRows);
}

async function _showRollWasteGrid(sprName, sprRow) {
	const ctx = await _loadWastageContext(sprName);
	const table = _rollWasteTable(ctx);
	const rows = (table.rows || []).map(_normalizePattyRow);
	const rollCols = _apiColsToDesk(table.columns, DESK_ROLL_WASTE_COLS);
	const content = `<div class="gwm-shell">
		<div class="gwm-card">
			<div class="gwm-section-title">${__("Roll Waste")}</div>
			${_dataCardsHtml(rows, { kind: "roll", showPrint: true })}
		</div>
		<div class="gwm-card" style="margin-top:12px;">
			<div class="gwm-section-title">${__("Table View")}</div>
			${_deskTableHtml(rollCols, rows, { showPrint: true })}
		</div>
	</div>`;

	const d = new frappe.ui.Dialog({
		title: __("Roll Waste") + ` · ${sprRow.order_code || ""}`,
		size: "extra-large",
		fields: [{ fieldname: "grid_html", fieldtype: "HTML", options: content }],
		primary_action_label: __("Close"),
		primary_action() {
			d.hide();
		},
	});
	d.show();
	_bindWastagePrint(d.$wrapper, sprName, table.resolved_fieldname || "custom_roll_waste", rows);
}

function _recycledWastageTable(ctx) {
	const tables = ctx?.tables || {};
	const direct = tables.custom_recycled_wastage_details;
	if ((direct?.rows || []).length) {
		return direct;
	}
	for (const [key, table] of Object.entries(tables)) {
		if (!table) {
			continue;
		}
		if (/recycl/i.test(key) || /recycl/i.test(table.child_doctype || "")) {
			if ((table.rows || []).length) {
				return table;
			}
		}
	}
	return direct || { rows: [], columns: [] };
}

export async function openGsmRecycleDialog(opts = {}) {
	_injectGwmStyles();
	const sprRow = await pickSessionSpr(opts.sessionSprList, opts);
	if (!sprRow) {
		return;
	}
	await _openRecycleMain(sprRow.spr_name, sprRow, opts);
}

async function _openRecycleMain(sprName, sprRow, opts) {
	const ctx = await _loadWastageContext(sprName);
	const recycled = _recycledWastageTable(ctx);
	const rows = (recycled.rows || []).map(_normalizePattyRow);
	const recycledCols = _apiColsToDesk(recycled.columns, DESK_RECYCLED_COLS);

	const content = `<div class="gwm-shell">
		<div class="gwm-actions">
			<button type="button" class="btn btn-default gwm-btn-patty">
				<span class="fa fa-eye" style="margin-right:6px;"></span>${__("View Patty Stock")}
			</button>
			<button type="button" class="btn btn-default gwm-btn-roll-waste">${__("Roll Waste")}</button>
		</div>
		<div class="gwm-card">
			<div class="gwm-section-title">${__("Recycled Wastage Details")}</div>
			${
				rows.length
					? _deskTableHtml(recycledCols, rows)
					: `<div class="gwm-empty">${__(
							"No recycled rows yet. Use View Patty Stock or Roll Waste to consume."
					  )}</div>`
			}
		</div>
	</div>`;

	const d = new frappe.ui.Dialog({
		title: __("Recycle") + ` · ${sprRow.order_code || ""} · ${sprName}`,
		size: "extra-large",
		fields: [{ fieldname: "body_html", fieldtype: "HTML", options: content }],
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
	if (!production_entry.spr_patty_stock || typeof production_entry.spr_patty_stock.open_dialog !== "function") {
		frappe.msgprint(__("Patty stock dialog not loaded."));
		return;
	}
	await production_entry.spr_patty_stock.open_dialog(sprName, {
		on_consume: async (picks, dialog) => {
			await frappe.call({
				method:
					"production_entry.production_planning.unified_production_entry_api.consume_gsm_recycled_wastage",
				args: {
					spr_name: sprName,
					patty_selections: JSON.stringify(picks),
				},
			});
			frappe.show_alert({ message: __("Added to Recycled Wastage Details"), indicator: "green" });
			if (dialog) {
				dialog.hide();
			}
			if (typeof onDone === "function") {
				onDone();
			}
		},
	});
}

async function _openRollWasteRecyclePicker(sprName, sprRow, onDone) {
	const ctx = await _loadWastageContext(sprName);
	const rows = ((ctx.tables || {}).custom_roll_waste || {}).rows || [];
	if (!rows.length) {
		frappe.msgprint(__("No roll waste rows on this SPR."));
		return;
	}

	const html = `<div class="gwm-shell gwm-card">
		<div class="gwm-section-title">${__("Roll Waste — select to recycle")}</div>
		<div class="gwm-table-wrap">
			<table class="gwm-desk-table">
				<thead><tr>
					<th class="gwm-check"><input type="checkbox" class="gwm-rw-all" /></th>
					<th>${__("Batch")}</th><th>${__("Job")}</th><th>${__("Quality")}</th>
					<th>${__("GSM")}</th><th class="gwm-num">${__("Width")}</th><th class="gwm-num">${__("Wastage Kg")}</th>
				</tr></thead>
				<tbody>${rows
					.map((r) => {
						const row = _normalizePattyRow(r);
						return `<tr>
					<td class="gwm-check"><input type="checkbox" class="gwm-rw-cb" data-name="${_esc(r.name)}" /></td>
					<td>${_esc(row.batch_no)}</td><td>${_esc(row.job_id)}</td>
					<td>${_esc(row.quality)}</td><td>${_esc(row.gsm)}</td>
					<td class="gwm-num">${_esc(row.width_inch)}</td><td class="gwm-num">${_fmtNum(row.wastage)}</td>
				</tr>`;
					})
					.join("")}</tbody>
			</table>
		</div>
	</div>`;

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
	_wireSelectAll(d.$wrapper, ".gwm-rw-cb", ".gwm-rw-all");
}
