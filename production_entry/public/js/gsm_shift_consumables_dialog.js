/* global frappe, __ */

const CONS_API = "production_entry.production_planning.shift_consumables_api";

function _esc(s) {
	return frappe.utils.escape_html(String(s ?? ""));
}

function _args(ctx) {
	return {
		run_date: ctx.run_date || "",
		shift: ctx.shift || "",
		custom_unit: ctx.custom_unit || "",
		gsm_shift_session: ctx.gsm_shift_session || "",
		doc_name: ctx.doc_name || "",
	};
}

function _tableHtml(rows) {
	if (!rows.length) {
		rows.push({ item_code: "", item_name: "", quantity: "", uom: "" });
	}
	const body = rows
		.map(
			(row, i) => `<tr data-idx="${i}">
			<td class="sc-item"><div class="sc-link"></div></td>
			<td class="sc-name"><input class="form-control input-sm" type="text" readonly value="${_esc(row.item_name || "")}"></td>
			<td class="sc-qty"><input class="form-control input-sm" type="number" min="0" step="0.001" value="${_esc(row.quantity || "")}"></td>
			<td class="sc-uom"><input class="form-control input-sm" type="text" readonly value="${_esc(row.uom || "")}"></td>
		</tr>`
		)
		.join("");
	return `<style>
		.sc-wrap { display:flex; flex-direction:column; gap:12px; }
		.sc-table { margin:0; font-size:12px; }
		.sc-table th, .sc-table td { vertical-align:middle; }
		.sc-link .frappe-control { margin:0; }
		.sc-link .form-control { min-width: 160px; }
	</style>
	<div class="sc-wrap">
		<table class="table table-bordered table-sm sc-table">
			<thead><tr>
				<th>${__("Item Code")}</th>
				<th>${__("Item Name")}</th>
				<th>${__("Quantity")}</th>
				<th>${__("UOM")}</th>
			</tr></thead>
			<tbody>${body}</tbody>
		</table>
		<div>
			<button type="button" class="btn btn-xs btn-primary" id="sc-add-row">${__("Add Row")}</button>
		</div>
	</div>`;
}

export async function openGsmShiftConsumablesDialog(opts = {}) {
	const ctx = {
		run_date: opts.run_date || opts.runDate || "",
		shift: opts.shift || "",
		custom_unit: (opts.custom_unit || opts.headerUnit || "").trim(),
		gsm_shift_session: opts.gsm_shift_session || opts.shiftSessionId || "",
		doc_name: "",
	};
	if (!ctx.custom_unit) {
		frappe.msgprint(__("Select a unit first."));
		return;
	}
	if (!ctx.run_date || !ctx.shift) {
		frappe.msgprint(__("Set Run Date and Shift first."));
		return;
	}

	const load = async () => {
		const res = await frappe.call({
			method: `${CONS_API}.get_shift_consumables`,
			args: _args(ctx),
		});
		const msg = res.message || {};
		ctx.doc_name = msg.name || ctx.doc_name;
		return msg;
	};

	let payload = await load();
	let rows = (payload.rows || []).map((r) => ({ ...r }));
	const linkControls = [];

	const d = new frappe.ui.Dialog({
		title: `${__("Shift Consumables")} — ${ctx.run_date} · ${ctx.shift} · ${ctx.custom_unit}`,
		size: "large",
		primary_action_label: __("Save"),
		primary_action: async () => {
			await saveRows();
			frappe.show_alert({ message: __("Shift consumables saved"), indicator: "green" });
		},
	});

	const $body = $('<div class="sc-body"></div>').appendTo(d.body);

	function readRows() {
		const next = [];
		$body.find("tbody tr").each(function (i) {
			const $tr = $(this);
			const ctrl = linkControls[i];
			next.push({
				item_code: (ctrl && ctrl.get_value()) || rows[i]?.item_code || "",
				item_name: $tr.find(".sc-name input").val() || "",
				quantity: $tr.find(".sc-qty input").val() || "",
				uom: $tr.find(".sc-uom input").val() || "",
			});
		});
		rows = next;
		return rows;
	}

	async function fillItem($tr, itemCode) {
		if (!itemCode) {
			$tr.find(".sc-name input").val("");
			$tr.find(".sc-uom input").val("");
			return;
		}
		const res = await frappe.call({
			method: `${CONS_API}.get_consumable_item_details`,
			args: { item_code: itemCode },
		});
		const msg = res.message || {};
		$tr.find(".sc-name input").val(msg.item_name || "");
		$tr.find(".sc-uom input").val(msg.uom || "");
	}

	const render = () => {
		linkControls.length = 0;
		$body.html(_tableHtml(rows));
		$body.find("tbody tr").each(function () {
			const $tr = $(this);
			const idx = Number($tr.attr("data-idx"));
			const ctrl = frappe.ui.form.make_control({
				df: {
					fieldtype: "Link",
					options: "Item",
					fieldname: "item_code",
					placeholder: __("Item Code"),
					only_select: 1,
				},
				parent: $tr.find(".sc-link").get(0),
				render_input: true,
				only_input: true,
			});
			ctrl.set_value(rows[idx]?.item_code || "");
			ctrl.$input.on("awesomplete-selectcomplete change", async () => {
				const val = ctrl.get_value();
				await fillItem($tr, val);
			});
			linkControls[idx] = ctrl;
		});
		$body.find("#sc-add-row").on("click", () => {
			readRows();
			rows.push({ item_code: "", item_name: "", quantity: "", uom: "" });
			render();
		});
	};

	async function saveRows() {
		readRows();
		d.get_primary_btn().prop("disabled", true);
		try {
			const res = await frappe.call({
				method: `${CONS_API}.save_shift_consumables`,
				args: {
					..._args(ctx),
					rows: JSON.stringify(rows.filter((r) => r.item_code)),
				},
			});
			payload = res.message || payload;
			ctx.doc_name = payload.name || ctx.doc_name;
			rows = (payload.rows || []).map((r) => ({ ...r }));
			if (!rows.length) {
				rows.push({ item_code: "", item_name: "", quantity: "", uom: "" });
			}
			render();
			return payload;
		} finally {
			d.get_primary_btn().prop("disabled", false);
		}
	}

	d.show();
	render();
}

frappe.provide("production_entry.gsm_shift_consumables");
production_entry.gsm_shift_consumables.openGsmShiftConsumablesDialog = openGsmShiftConsumablesDialog;
