// SPR form — transfer dialog (Vue from scheduler.bundle.js, or frappe.ui.Dialog fallback)
frappe.provide("production_entry.spr_transfer");

production_entry.spr_transfer = production_entry.spr_transfer || {};

const SPR_TRANSFER_API = "production_entry.production_planning.transfer_logistics";

production_entry.spr_transfer.open = function (frm) {
	if (!frm || !frm.doc || !frm.doc.name) {
		return;
	}
	if (cint(frm.doc.docstatus) !== 1) {
		frappe.msgprint(__("Submit the SPR before transfer."));
		return;
	}
	if (
		typeof production_scheduler !== "undefined" &&
		typeof production_scheduler.openSprTransferDialog === "function"
	) {
		try {
			production_scheduler.openSprTransferDialog(frm.doc.name);
			return;
		} catch (e) {
			console.error("SPR transfer Vue dialog failed, using fallback", e);
		}
	}
	production_entry.spr_transfer.open_fallback_dialog(frm.doc.name);
};

production_entry.spr_transfer.open_fallback_dialog = function (sprName) {
	const state = {
		sprName,
		fromCompany: "",
		toOptions: [],
		customer: "",
		unit: "",
		batches: [],
	};

	const d = new frappe.ui.Dialog({
		title: __("Transfer rolls — {0}", [sprName]),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "spr_transfer_html",
			},
		],
		primary_action_label: __("Transfer & create Stock Entry"),
		primary_action() {
			production_entry.spr_transfer.submit_fallback_dialog(d, state);
		},
	});

	d.show();
	d.$wrapper.find(".modal-dialog").css("max-width", "920px");
	const $w = d.fields_dict.spr_transfer_html.$wrapper;
	$w.html('<p class="text-muted">' + __("Loading transfer data…") + "</p>");

	frappe.call({
		method: SPR_TRANSFER_API + ".get_spr_transfer_context",
		args: { spr_name: sprName },
		callback(r) {
			const ctx = r.message || {};
			state.fromCompany = ctx.from_company || "";
			state.toOptions = ctx.to_company_options || [];
			state.customer = ctx.customer || "";
			state.unit = ctx.unit || "";
			const rollMap = {};
			(ctx.rolls || []).forEach((row) => {
				if (row.batch_no) {
					rollMap[row.batch_no] = row;
				}
			});

			frappe.call({
				method: SPR_TRANSFER_API + ".get_spr_produced_batches",
				args: {
					spr_name: sprName,
					from_company: state.fromCompany,
				},
				callback(r2) {
					const produced = r2.message || [];
					state.batches = produced.map((b) => {
						const meta = rollMap[b.batch_no] || {};
						const qty = parseFloat(b.qty || meta.qty) || 1;
						return {
							batch_no: b.batch_no,
							item_code: b.item_code || meta.item_code || "",
							party_code: meta.party_code || "",
							planning_table_row: meta.planning_table_row || "",
							planning_sheet: meta.planning_sheet || "",
							qty,
							selected: false,
						};
					});
					production_entry.spr_transfer.render_fallback_dialog($w, d, state);
				},
				error() {
					$w.html('<p class="text-danger">' + __("Failed to load batches.") + "</p>");
				},
			});
		},
		error() {
			$w.html('<p class="text-danger">' + __("Failed to load SPR transfer context.") + "</p>");
		},
	});
};

production_entry.spr_transfer.render_fallback_dialog = function ($w, d, state) {
	const toOpts = (state.toOptions || [])
		.map(
			(c) =>
				'<option value="' +
				frappe.utils.escape_html(c.name) +
				'">' +
				frappe.utils.escape_html(c.label || c.name) +
				"</option>"
		)
		.join("");

	let rows = "";
	(state.batches || []).forEach((b, i) => {
		const disabled = !b.planning_table_row;
		rows +=
			"<tr" +
			(disabled ? ' class="text-muted"' : "") +
			">" +
			'<td><input type="checkbox" class="spr-tr-batch-chk" data-idx="' +
			i +
			'"' +
			(disabled ? " disabled" : "") +
			"></td>" +
			"<td>" +
			frappe.utils.escape_html(b.batch_no) +
			"</td>" +
			"<td>" +
			frappe.utils.escape_html(b.item_code) +
			"</td>" +
			"<td>" +
			frappe.utils.escape_html(b.party_code || "—") +
			"</td>" +
			'<td><input type="number" class="form-control input-sm spr-tr-batch-qty" data-idx="' +
			i +
			'" value="' +
			b.qty +
			'" step="0.01" min="0"' +
			(disabled ? " disabled" : "") +
			"></td>" +
			"</tr>";
	});

	const html =
		'<div class="spr-transfer-fallback" style="padding:4px 0">' +
		'<div class="row" style="margin-bottom:12px">' +
		'<div class="col-sm-6"><label><strong>' +
		__("From company") +
		"</strong></label><div>" +
		frappe.utils.escape_html(state.fromCompany || "—") +
		"</div></div>" +
		'<div class="col-sm-6"><label><strong>' +
		__("To company") +
		' <span class="text-danger">*</span></strong></label>' +
		'<select class="form-control spr-tr-to-company"><option value="">' +
		__("Select destination…") +
		"</option>" +
		toOpts +
		"</select></div></div>" +
		'<div class="row" style="margin-bottom:12px">' +
		'<div class="col-sm-6"><label><strong>' +
		__("Nature of Processing") +
		' <span class="text-danger">*</span></strong></label>' +
		'<select class="form-control spr-tr-nature">' +
		'<option value="">' +
		__("— Select —") +
		"</option>" +
		'<option value="Lamination">Lamination</option>' +
		'<option value="Printing">Printing</option>' +
		'<option value="Slitting">Slitting</option>' +
		'<option value="Rewinding">Rewinding</option>' +
		'<option value="Sheet Cutting">Sheet Cutting</option>' +
		'<option value="FG Transfer">FG Transfer</option>' +
		'<option value="Other">Other</option>' +
		"</select></div>" +
		'<div class="col-sm-6 spr-tr-nature-other-wrap" style="display:none">' +
		'<label><strong>' +
		__("Specify") +
		"</strong></label>" +
		'<input type="text" class="form-control spr-tr-nature-other" placeholder="' +
		__("Enter nature of processing") +
		'">' +
		"</div></div>" +
		(state.batches.length
			? '<table class="table table-bordered table-condensed"><thead><tr><th></th><th>' +
			  __("Batch No") +
			  "</th><th>" +
			  __("Item") +
			  "</th><th>" +
			  __("Order") +
			  "</th><th>" +
			  __("Qty (Kg)") +
			  "</th></tr></thead><tbody>" +
			  rows +
			  "</tbody></table>"
			: '<p class="text-muted">' + __("No transferable batches on this SPR.") + "</p>") +
		'<p class="text-warning small">' +
		__("Rows without a Planning Table link are disabled. Link this SPR on the planning sheet first.") +
		"</p></div>";

	$w.html(html);

	$w.find(".spr-tr-nature").on("change", function () {
		const show = $(this).val() === "Other";
		$w.find(".spr-tr-nature-other-wrap").toggle(show);
	});

	$w.find(".spr-tr-batch-chk").on("change", function () {
		const idx = parseInt($(this).attr("data-idx"), 10);
		if (state.batches[idx]) {
			state.batches[idx].selected = $(this).is(":checked");
		}
	});

	$w.find(".spr-tr-batch-qty").on("change input", function () {
		const idx = parseInt($(this).attr("data-idx"), 10);
		const n = parseFloat($(this).val());
		if (state.batches[idx] && Number.isFinite(n)) {
			state.batches[idx].qty = n;
		}
	});

	d.$wrapper.data("spr_transfer_state", state);
};

production_entry.spr_transfer.submit_fallback_dialog = function (d, state) {
	const $w = d.fields_dict.spr_transfer_html.$wrapper;
	const toCompany = ($w.find(".spr-tr-to-company").val() || "").trim();
	let nature = ($w.find(".spr-tr-nature").val() || "").trim();
	if (nature === "Other") {
		nature = ($w.find(".spr-tr-nature-other").val() || "").trim();
	}
	if (!toCompany) {
		frappe.msgprint(__("Select destination company."));
		return;
	}
	if (!nature) {
		frappe.msgprint(__("Select Nature of Processing."));
		return;
	}

	const lines = (state.batches || [])
		.filter((b) => b.selected && b.planning_table_row && b.batch_no && parseFloat(b.qty) > 0)
		.map((b) => ({
			planning_table_row: b.planning_table_row,
			planning_sheet: b.planning_sheet,
			party_code: b.party_code,
			customer_name: state.customer,
			item_code: b.item_code,
			unit: state.unit,
			spr_name: state.sprName,
			batch_no: b.batch_no,
			qty: parseFloat(b.qty),
			uom: "Kg",
		}));

	if (!lines.length) {
		frappe.msgprint(__("Select at least one batch with qty."));
		return;
	}

	d.get_primary_btn().prop("disabled", true);
	frappe.call({
		method: SPR_TRANSFER_API + ".create_and_approve_transfer_from_spr",
		args: {
			spr_name: state.sprName,
			from_company: state.fromCompany,
			to_company: toCompany,
			to_destination_label: __("Transfer to {0}", [toCompany]),
			nature_of_processing: nature,
			lines: JSON.stringify(lines),
		},
		callback(r) {
			d.hide();
			const ste = (r.message && r.message.stock_entry) || "";
			const ta = (r.message && r.message.transfer_approval) || "";
			frappe.show_alert({
				message: ste ? __("Stock Entry {0} created", [ste]) : __("Transfer {0} approved", [ta]),
				indicator: "green",
			});
			if (ste) {
				frappe.set_route("Form", "Stock Entry", ste);
			}
		},
		error() {
			d.get_primary_btn().prop("disabled", false);
		},
	});
};
