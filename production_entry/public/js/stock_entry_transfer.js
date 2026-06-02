// Transfer STE: barcode scans update scanned_qty only; approved qty stays fixed.

function _is_material_transfer(frm) {
	return (frm.doc.stock_entry_type || "").trim() === "Material Transfer";
}

function _disable_native_barcode_scanner(frm) {
	if (!frm.barcode_scanner) return;
	const noop = function () {};
	frm.barcode_scanner.process_scan = noop;
	frm.barcode_scanner.clean_up = noop;
	frm.barcode_scanner.update_item_quantity = noop;
	frm.barcode_scanner.update_item = noop;
	frm.barcode_scanner.scan_barcode = noop;
}

function _protect_transfer_row_qty(frm) {
	if (!_is_material_transfer(frm)) return;
	(frm.doc.items || []).forEach((r) => {
		if (r && r.name) {
			r._protected_qty = Number(r._protected_qty != null ? r._protected_qty : r.qty || 0);
		}
	});
}

function _bind_scan_input(frm) {
	if (!_is_material_transfer(frm)) return;
	const fields = ["scan_barcode", "custom_barcode_scanner"];
	fields.forEach((fieldname) => {
		if (!frm.fields_dict[fieldname] || !frm.fields_dict[fieldname].$input) return;
		const $input = frm.fields_dict[fieldname].$input;
		$input.off(".transfer_scan");
		$input.on("change.transfer_scan keypress.transfer_scan", function (e) {
			if (e.type === "keypress" && e.which !== 13) return;
			const val = ($input.val() || "").trim();
			if (!val) return;
			if (fieldname === "scan_barcode") {
				frappe.model.set_value(frm.doctype, frm.docname, "scan_barcode", val).then(() => {
					frm.trigger("process_barcode_scan");
				});
			} else {
				frappe.model.set_value(frm.doctype, frm.docname, "custom_barcode_scanner", val).then(() => {
					frm.trigger("process_barcode_scan");
				});
			}
		});
	});
}

function _apply_scan_to_locals(frm, row_name, scanned_qty, qty) {
	const cdt = "Stock Entry Detail";
	const row = (frm.doc.items || []).find((r) => r.name === row_name);
	if (!row) return;
	row.scanned_qty = scanned_qty;
	row.custom_scanned_qty = scanned_qty;
	row.qty = qty;
	row._protected_qty = qty;
	frm.refresh_field("items");
}

function _scan_locally(frm, barcode) {
	const expected_item = frm.doc.items && frm.doc.items.length ? frm.doc.items[0].item_code : null;
	const existing_row = (frm.doc.items || []).find(
		(r) => r.batch_no === barcode || r.custom_roll_no === barcode
	);
	if (!existing_row) {
		frappe.msgprint({
			title: __("Batch Not Found"),
			indicator: "orange",
			message: __("The scanned batch <b>{0}</b> is not in the approved list.", [barcode]),
		});
		frappe.utils.play_sound("error");
		return;
	}
	if (expected_item && existing_row.item_code !== expected_item) {
		frappe.msgprint({
			title: __("Wrong Item"),
			indicator: "red",
			message: __("The scanned batch belongs to <b>{0}</b>, but we are transferring <b>{1}</b>.", [
				existing_row.item_code,
				expected_item,
			]),
		});
		frappe.utils.play_sound("error");
		return;
	}

	const approved = Number(existing_row._protected_qty != null ? existing_row._protected_qty : existing_row.qty || 0);
	const cur = Math.max(Number(existing_row.scanned_qty || 0), Number(existing_row.custom_scanned_qty || 0));
	const new_scanned = approved > 0 && cur + 1 >= approved ? approved : cur + 1;
	const updates = { custom_scanned_qty: new_scanned, qty: approved };
	if (frappe.meta.has_field("Stock Entry Detail", "scanned_qty")) {
		updates.scanned_qty = new_scanned;
	}

	frappe.model.set_value(existing_row.doctype, existing_row.name, updates).then(() => {
		existing_row._protected_qty = approved;
		frm.refresh_field("items");
		frappe.show_alert({
			message: __("Row #{0}: Scanned {1} / {2}", [existing_row.idx, new_scanned, approved]),
			indicator: "green",
		});
		frappe.utils.play_sound("submit");
	});
}

frappe.ui.form.on("Stock Entry", {
	setup(frm) {
		_disable_native_barcode_scanner(frm);
		if (frm.script_manager && frm.script_manager.events) {
			frm.script_manager.events.scan_barcode = [
				function (f) {
					if (_is_material_transfer(f)) f.trigger("process_barcode_scan");
				},
			];
			frm.script_manager.events.custom_barcode_scanner = [
				function (f) {
					if (_is_material_transfer(f)) f.trigger("process_barcode_scan");
				},
			];
		}
	},

	scan_barcode(frm) {
		if (_is_material_transfer(frm)) {
			frm.trigger("process_barcode_scan");
		}
	},

	custom_barcode_scanner(frm) {
		if (_is_material_transfer(frm)) {
			frm.trigger("process_barcode_scan");
		}
	},

	refresh(frm) {
		_disable_native_barcode_scanner(frm);
		_protect_transfer_row_qty(frm);
		_bind_scan_input(frm);

		const co = (frm.doc.custom_transfer_to_company || "").trim();
		if (co) {
			if (frm.fields_dict.party_type && !frm.doc.party_type) {
				frm.set_value("party_type", "Company");
			}
			if (frm.fields_dict.party && !frm.doc.party) {
				frm.set_value("party", co);
			}
		}

		if (frm.doc.docstatus === 0 && _is_material_transfer(frm) && frm.doc.items && frm.doc.items.length > 0) {
			frm.add_custom_button(
				__("Approved Rolls"),
				() => {
					frappe.call({
						method: "frappe.client.get_list",
						args: {
							doctype: "Transfer Approval",
							filters: { stock_entry: frm.doc.name },
							fields: ["name"],
						},
						callback: function (r) {
							if (r.message && r.message.length > 0) {
								let ta_name = r.message[0].name;
								frappe.call({
									method: "frappe.client.get",
									args: { doctype: "Transfer Approval", name: ta_name },
									callback: function (r2) {
										if (r2.message) {
											let grouped = {};
											(r2.message.lines || []).forEach((row) => {
												if (!grouped[row.item_code]) grouped[row.item_code] = [];
												grouped[row.item_code].push(row);
											});
											let html = "";
											for (let ic in grouped) {
												html += `<h4>${ic}</h4>`;
												html +=
													"<table class='table table-bordered'><tr><th>Batch No</th><th>Qty</th></tr>";
												grouped[ic].forEach((row) => {
													html += `<tr><td>${row.batch_no || ""}</td><td>${row.qty}</td></tr>`;
												});
												html += "</table><br>";
											}
											let d = new frappe.ui.Dialog({
												title: "Approved Rolls",
												fields: [
													{
														fieldtype: "HTML",
														fieldname: "html_content",
														options: html,
													},
												],
											});
											d.show();
										}
									},
								});
							} else {
								frappe.msgprint("No Transfer Approval linked to this Stock Entry.");
							}
						},
					});
				},
				__("Actions")
			);
		}

		if (frm.doc.docstatus === 1 && frm.doc.items && frm.doc.items.length > 0) {
			frm.add_custom_button(__("Sales Invoice"), () => {
				frappe.model.open_mapped_doc({
					method: "production_entry.stock_entry_sales_invoice.make_sales_invoice_from_stock_entry",
					frm: frm,
				});
			}, __("Create"));
		}
	},

	validate(frm) {
		if (_is_material_transfer(frm) && frm.doc.items) {
			let pending = frm.doc.items.filter(
				(r) => (r.qty || 0) > ((r.scanned_qty || r.custom_scanned_qty) || 0) + 0.01
			);
			if (pending.length > 0) {
				let pending_items = pending.map((r) => r.item_code).join(", ");
				frappe.msgprint({
					title: "Validation Error",
					indicator: "red",
					message: `You must scan all approved rolls! Missing scanned quantity for: <b>${pending_items}</b>.`,
				});
				frappe.validated = false;
			}
		}
	},

	process_barcode_scan: function (frm) {
		let barcode = (frm.doc.scan_barcode || frm.doc.custom_barcode_scanner || "").trim();
		if (!barcode || !_is_material_transfer(frm)) return;

		if (frm.doc.scan_barcode) frappe.model.set_value(frm.doctype, frm.docname, "scan_barcode", "");
		if (frm.doc.custom_barcode_scanner)
			frappe.model.set_value(frm.doctype, frm.docname, "custom_barcode_scanner", "");

		if (!frm.doc.name || frm.is_new()) {
			_scan_locally(frm, barcode);
			return;
		}

		frappe.call({
			method: "production_entry.production_planning.transfer_logistics.record_transfer_barcode_scan",
			args: { stock_entry: frm.doc.name, barcode: barcode },
			callback: function (r) {
				const msg = r.message || {};
				if (!msg.ok) {
					frappe.msgprint({
						title: __("Scan failed"),
						indicator: "red",
						message: msg.error || __("Could not record scan"),
					});
					frappe.utils.play_sound("error");
					return;
				}
				_apply_scan_to_locals(frm, msg.row_name, msg.scanned_qty, msg.qty);
				frappe.show_alert({
					message: __("Row #{0}: Scanned {1} / {2}", [msg.idx, msg.scanned_qty, msg.qty]),
					indicator: "green",
				});
				frappe.utils.play_sound("submit");
			},
		});
	},
});

frappe.ui.form.on("Stock Entry Detail", {
	qty: function (frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);
		if (
			_is_material_transfer(frm) &&
			row._protected_qty !== undefined &&
			row.qty !== row._protected_qty
		) {
			frappe.model.set_value(cdt, cdn, "qty", row._protected_qty);
		}
	},
});
