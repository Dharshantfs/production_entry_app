// Shared View Patty Stock dialog — desk SPR toolbar and GSM Recycle use the same API + UI.
frappe.provide("production_entry.spr_patty_stock");

const _PATTY_STOCK_RPC =
	"production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_available_patty_stock";

const _STOCK_COLS = [
	{ key: "batch_no", label: "Batch No", filter: true, minW: "108px" },
	{ key: "quality", label: "Quality", filter: true, minW: "88px" },
	{ key: "color", label: "Color", filter: true, minW: "88px" },
	{ key: "gsm", label: "GSM", filter: true, num: true, minW: "52px" },
	{ key: "width_inch", label: "Width", filter: true, num: true, minW: "64px" },
	{ key: "available_kg", label: "Avail (Kg)", filter: false, num: true, minW: "72px" },
];

const _PATTY_STOCK_CSS = `
<style>
.spr-patty-dialog .modal-dialog { max-width: min(96vw, 920px); margin: 1.2rem auto; }
.spr-patty-dialog .modal-body { padding: 12px 16px 8px; overflow: hidden; }
.spr-patty-stock-wrap { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.spr-patty-section { font-weight: 700; font-size: 13px; color: #334155; }
.spr-patty-scroll { overflow: auto; max-height: min(58vh, 480px); border: 1px solid #e2e8f0; border-radius: 8px; background: #fff; }
.spr-patty-table { width: 100%; min-width: 640px; margin: 0; table-layout: fixed; font-size: 12px; }
.spr-patty-table thead th { position: sticky; top: 0; z-index: 2; background: #f8fafc; vertical-align: top; }
.spr-patty-table th, .spr-patty-table td { padding: 6px 8px; word-break: break-word; overflow-wrap: anywhere; white-space: normal; }
.spr-patty-table .spr-patty-check { width: 36px; min-width: 36px; text-align: center; }
.spr-patty-num { text-align: right; font-variant-numeric: tabular-nums; }
.spr-patty-filter { width: 100%; max-width: 100%; box-sizing: border-box; font-size: 11px; padding: 3px 6px; }
.spr-patty-empty { padding: 24px; text-align: center; color: #64748b; }
.spr-patty-row:hover { background: #f1f5f9; }
</style>`;

function _esc(s) {
	return frappe.utils.escape_html(String(s ?? ""));
}

function _fmtNum(v, dp) {
	const n = parseFloat(v);
	if (!Number.isFinite(n)) {
		return "";
	}
	return n.toFixed(dp == null ? 3 : dp);
}

function _normalizeStockRow(row) {
	row = row || {};
	return {
		...row,
		name: row.batch_no || row.name || "",
		batch_no: row.batch_no || (String(row.name || "").includes("/") ? row.name : "") || "",
		quality: row.quality || "",
		color: row.color || row.colour || "",
		gsm: row.gsm != null && row.gsm !== "" ? row.gsm : "",
		width_inch: (function () {
			const w = parseFloat(row.width_inch != null && row.width_inch !== "" ? row.width_inch : row.width);
			return Number.isFinite(w) && w > 0 ? w : parseFloat(row.custom_width_inch) || "";
		})(),
		available_kg: row.available_kg != null ? row.available_kg : row.available || row.qty || 0,
	};
}

production_entry.spr_patty_stock.fetch = async function (sprName) {
	const res = await frappe.call({
		method: _PATTY_STOCK_RPC,
		args: { spr_name: sprName || "" },
	});
	const rows = res.message;
	let parsed = [];
	if (Array.isArray(rows)) {
		parsed = rows.map(_normalizeStockRow);
	} else if (rows && Array.isArray(rows.stock)) {
		parsed = rows.stock.map(_normalizeStockRow);
	}
	parsed = parsed.filter((r) => parseFloat(r.available_kg) > 0);
	if (parsed.length) {
		return parsed;
	}

	const gsmRes = await frappe.call({
		method:
			"production_entry.production_planning.unified_production_entry_api.get_gsm_available_patty_stock",
		args: { spr_name: sprName || "" },
	});
	const gsmRows = gsmRes.message?.stock || [];
	return gsmRows.map(_normalizeStockRow).filter((r) => parseFloat(r.available_kg) > 0);
};

function _stockTableHtml(stock) {
	if (!stock.length) {
		return `${_PATTY_STOCK_CSS}<div class="spr-patty-empty">${__("No patty stock available.")}</div>`;
	}
	const head = _STOCK_COLS.map(
		(c) =>
			`<th class="${c.num ? "spr-patty-num" : ""}" style="min-width:${c.minW}">${__(c.label)}</th>`
	).join("");
	const filters = _STOCK_COLS.map((c, i) =>
		c.filter
			? `<th style="min-width:${c.minW}"><input type="text" class="spr-patty-filter" data-col="${i}" placeholder="${__("Filter")}" /></th>`
			: `<th style="min-width:${c.minW}"></th>`
	).join("");
	const body = stock
		.map((raw, idx) => {
			const row = _normalizeStockRow(raw);
			const key = row.batch_no || row.name || String(idx);
			const cells = _STOCK_COLS.map((c) => {
				let v = row[c.key];
				if (c.num) {
					v = c.key === "gsm" ? _fmtNum(v, 0) : _fmtNum(v, 3);
				}
				return `<td class="${c.num ? "spr-patty-num" : ""}">${_esc(v)}</td>`;
			}).join("");
			const search = _STOCK_COLS.map((c) => String(row[c.key] ?? "")).join("|");
			return `<tr class="spr-patty-row" data-key="${_esc(key)}" data-search="${_esc(search)}">
				<td class="spr-patty-check"><input type="checkbox" class="spr-patty-cb" data-key="${_esc(key)}" /></td>
				${cells}
			</tr>`;
		})
		.join("");
	return `${_PATTY_STOCK_CSS}
	<div class="spr-patty-stock-wrap">
		<div class="spr-patty-section">${__("Stock List")}</div>
		<div class="spr-patty-scroll">
			<table class="table table-bordered spr-patty-table">
				<thead>
					<tr><th class="spr-patty-check"><input type="checkbox" class="spr-patty-all" title="${__("Select all")}" /></th>${head}</tr>
					<tr><th></th>${filters}</tr>
				</thead>
				<tbody>${body}</tbody>
			</table>
		</div>
	</div>`;
}

function _wirePattyStockDialog($wrapper, stock) {
	$wrapper.on("input", ".spr-patty-filter", function () {
		const filters = [];
		$wrapper.find(".spr-patty-filter").each(function () {
			filters.push({
				col: parseInt($(this).data("col"), 10),
				val: String($(this).val() || "").trim().toLowerCase(),
			});
		});
		$wrapper.find(".spr-patty-row").each(function () {
			const parts = String($(this).data("search") || "").split("|");
			let show = true;
			for (const f of filters) {
				if (!f.val) {
					continue;
				}
				if (!String(parts[f.col] || "").toLowerCase().includes(f.val)) {
					show = false;
					break;
				}
			}
			$(this).toggle(show);
		});
	});
	$wrapper.on("change", ".spr-patty-all", function () {
		const on = $(this).prop("checked");
		$wrapper.find(".spr-patty-row:visible .spr-patty-cb").prop("checked", on);
	});
}

function _pattyConsumePayload(row) {
	const n = _normalizeStockRow(row);
	const kg = parseFloat(n.available_kg);
	const qty = Number.isFinite(kg) && kg > 0 ? kg : 0;
	const batch = String(n.batch_no || "").trim();
	return {
		batch_no: batch,
		item_code: n.item_code || "",
		quality: n.quality || "",
		color: n.color || "",
		gsm: n.gsm,
		width_inch: (function () {
			const w = parseFloat(n.width_inch);
			return Number.isFinite(w) && w > 0 ? w : 0;
		})(),
		available_kg: qty,
		wastage: qty,
		recycled: qty,
	};
}

production_entry.spr_patty_stock.open_dialog = async function (sprName, options) {
	options = options || {};
	const stock = await production_entry.spr_patty_stock.fetch(sprName);
	const d = new frappe.ui.Dialog({
		title: __("Available Patty Stock"),
		size: "large",
		fields: [{ fieldname: "stock_html", fieldtype: "HTML", options: _stockTableHtml(stock) }],
	});
	d.$wrapper.addClass("spr-patty-dialog");
	if (typeof options.on_consume === "function") {
		d.set_primary_action(__("Consume Selected"), async () => {
			const picks = [];
			d.$wrapper.find(".spr-patty-cb:checked").each(function () {
				const key = String($(this).attr("data-key") || $(this).data("key") || "");
				const row = stock.find((r, i) => String(r.batch_no || r.name || i) === key);
				if (row) {
					picks.push(_pattyConsumePayload(row));
				}
			});
			if (!picks.length) {
				frappe.msgprint(__("Select at least one row."));
				return;
			}
			d.get_primary_btn().prop("disabled", true);
			try {
				await options.on_consume(picks, d);
			} finally {
				d.get_primary_btn().prop("disabled", false);
			}
		});
	}
	d.show();
	_wirePattyStockDialog(d.$wrapper, stock);
	return d;
};
