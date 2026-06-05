// Transfer STE: barcode scans update scanned_qty only; approved qty stays fixed.

function _is_material_transfer(frm) {
	return (frm.doc.stock_entry_type || "").trim() === "Material Transfer";
}

function _externalTransferFieldname() {
	const candidates = [
		"custom_external_transfer",
		"external_transfer",
		"is_external_transfer",
		"ge_external_transfer",
	];
	for (const f of candidates) {
		if (frappe.meta.has_field("Stock Entry", f)) return f;
	}
	return "";
}

/** Scan / approved-roll rules only for logistics Transfer Approval STE — not manual Material Transfer. */
function _is_logistics_material_transfer(frm) {
	if (!_is_material_transfer(frm)) return false;
	const fn = _externalTransferFieldname();
	if (fn && cint(frm.doc[fn])) return true;
	if (frm._pe_logistics_transfer === true) return true;
	return false;
}

function cint(v) {
	const n = parseInt(v, 10);
	return Number.isFinite(n) ? n : 0;
}

function _refreshLogisticsTransferFlag(frm) {
	frm._pe_logistics_transfer = false;
	if (!_is_material_transfer(frm) || !frm.doc.name || frm.is_new()) return;
	frappe.call({
		method: "production_entry.production_planning.transfer_logistics.stock_entry_is_logistics_transfer",
		args: { stock_entry: frm.doc.name },
		async: false,
		callback(r) {
			frm._pe_logistics_transfer = !!(r.message);
			frm.refresh_fields();
		},
	});
}

function _disable_native_barcode_scanner(frm) {
	if (!_is_logistics_material_transfer(frm)) return;
	if (frm.barcode_scanner) {
		const noop = function () {};
		frm.barcode_scanner.process_scan = noop;
		frm.barcode_scanner.clean_up = noop;
		frm.barcode_scanner.update_item_quantity = noop;
		frm.barcode_scanner.update_item = noop;
		frm.barcode_scanner.scan_barcode = noop;
	}
	["scan_barcode", "custom_barcode_scanner"].forEach((fieldname) => {
		const fd = frm.fields_dict[fieldname];
		if (!fd || !fd.$input) return;
		fd.$input.off("change.barcode_scan");
		fd.$input.off("keydown.barcode_scan");
	});
}

function _protect_transfer_row_qty(frm) {
	if (!_is_logistics_material_transfer(frm)) return;
	(frm.doc.items || []).forEach((r) => {
		if (r && r.name) {
			r._protected_qty = Number(r._protected_qty != null ? r._protected_qty : r.qty || 0);
		}
	});
}

function _bind_scan_input(frm) {
	if (!_is_logistics_material_transfer(frm)) return;
	const fields = ["scan_barcode", "custom_barcode_scanner"];
	fields.forEach((fieldname) => {
		if (!frm.fields_dict[fieldname] || !frm.fields_dict[fieldname].$input) return;
		const $input = frm.fields_dict[fieldname].$input;
		$input.off(".transfer_scan");
		$input.on("keypress.transfer_scan", function (e) {
			if (e.which !== 13) return;
			e.preventDefault();
			e.stopImmediatePropagation();
			const val = ($input.val() || "").trim();
			$input.val("");
			if (frm.doc[fieldname]) frm.doc[fieldname] = "";
			if (val) _run_transfer_scan(frm, val);
		});
	});
}

function _run_transfer_scan(frm, barcode) {
	if (!barcode || !_is_logistics_material_transfer(frm)) return;
	if (frm._pe_scan_busy) return;
	frm._pe_scan_busy = true;
	const done = () => {
		setTimeout(() => {
			frm._pe_scan_busy = false;
		}, 400);
	};

	if (!frm.doc.name || frm.is_new()) {
		_scan_locally(frm, barcode);
		done();
		return;
	}

	frappe.call({
		method: "production_entry.production_planning.transfer_logistics.record_transfer_barcode_scan",
		args: { stock_entry: frm.doc.name, barcode: barcode },
		callback: function (r) {
			const msg = r.message || {};
			if (!msg.ok) {
				_scan_locally(frm, barcode);
				done();
				return;
			}
			_apply_scan_to_locals(frm, msg.row_name, msg.scanned_qty, msg.qty);
			frappe.show_alert({
				message: __("Row #{0}: Scanned {1} / {2}", [msg.idx, msg.scanned_qty, msg.qty]),
				indicator: "green",
			});
			frappe.utils.play_sound("submit");
			done();
		},
		error: function () {
			_scan_locally(frm, barcode);
			done();
		},
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

function _normalizeTransferScan(raw) {
	let s = (raw || "").trim().toUpperCase().replace(/\s+/g, "");
	s = s.replace(/\*+$/, "");
	if (s.startsWith("#S")) s = "JS" + s.slice(2);
	else if (s.startsWith("IS-")) s = "JS-" + s.slice(3);
	else if (s.startsWith("IS") && s.length > 2) s = "JS" + s.slice(2);
	for (const prefix of ["JVE", "TTT", "VTP", "JS", "JV", "TS", "TT", "VR", "VT"]) {
		if (new RegExp(`^${prefix}\\d`).test(s)) {
			s = `${prefix}-` + s.slice(prefix.length);
			break;
		}
	}
	if (/^\d{6,}\/\d/.test(s)) s = "JS-" + s;
	return s;
}

function _batchMatchKey(v) {
	return _normalizeTransferScan(v).replace(/[^A-Z0-9/]/g, "");
}

function _transferScanCandidates(raw) {
	const cands = [];
	const add = (v) => {
		v = (v || "").trim();
		if (v && !cands.includes(v)) cands.push(v);
	};
	add(raw);
	add((raw || "").toUpperCase());
	const norm = _normalizeTransferScan(raw);
	add(norm);
	add(_batchMatchKey(norm));
	const m = norm.match(/\/(\d+)/);
	if (m) {
		add("/" + m[1]);
		if (m[1].length === 1) add("/" + m[1] + "0");
	}
	return cands;
}

function _find_transfer_row_for_barcode(frm, barcode) {
	const rows = frm.doc.items || [];
	const cands = _transferScanCandidates(barcode);
	for (const cand of cands) {
		const ck = _batchMatchKey(cand);
		for (const r of rows) {
			const bn = (r.batch_no || "").trim();
			const roll = (r.custom_roll_no || "").trim();
			if (cand === bn || cand === roll || ck === _batchMatchKey(bn)) return r;
		}
	}
	for (const cand of cands) {
		const m = _batchMatchKey(cand).match(/\/(\d+)$/);
		if (!m) continue;
		const suf = "/" + m[1];
		let matched = rows.filter((r) => _batchMatchKey(r.batch_no || "").includes(suf));
		if (matched.length === 1) return matched[0];
		if (m[1].length === 1) {
			const suf10 = "/" + m[1] + "0";
			matched = rows.filter((r) => _batchMatchKey(r.batch_no || "").endsWith(suf10));
			if (matched.length === 1) return matched[0];
		}
	}
	return null;
}

function _scan_locally(frm, barcode) {
	const existing_row = _find_transfer_row_for_barcode(frm, barcode);
	if (!existing_row) {
		frappe.msgprint({
			title: __("Batch Not Found"),
			indicator: "orange",
			message: __("The scanned batch <b>{0}</b> is not in the approved list.", [barcode]),
		});
		frappe.utils.play_sound("error");
		return;
	}

	const approved = Number(existing_row._protected_qty != null ? existing_row._protected_qty : existing_row.qty || 0);
	const new_scanned = approved > 0 ? approved : 0;
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
		if (!_is_logistics_material_transfer(frm)) return;
		const val = (frm.doc.scan_barcode || "").trim();
		if (val) {
			frm.doc.scan_barcode = "";
			_run_transfer_scan(frm, val);
		}
	},

	custom_barcode_scanner(frm) {
		if (!_is_logistics_material_transfer(frm)) return;
		const val = (frm.doc.custom_barcode_scanner || "").trim();
		if (val) {
			frm.doc.custom_barcode_scanner = "";
			_run_transfer_scan(frm, val);
		}
	},

	refresh(frm) {
		_refreshLogisticsTransferFlag(frm);
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

		if (
			frm.doc.docstatus === 0 &&
			_is_logistics_material_transfer(frm) &&
			frm.doc.items &&
			frm.doc.items.length > 0
		) {
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

	before_submit(frm) {
		if (!_is_logistics_material_transfer(frm) || !frm.doc.items) {
			return;
		}
		const pending = frm.doc.items.filter(
			(r) => (r.qty || 0) > ((r.scanned_qty || r.custom_scanned_qty) || 0) + 0.01
		);
		if (pending.length > 0) {
			const pending_items = pending.map((r) => r.item_code).join(", ");
			frappe.msgprint({
				title: "Scan validation",
				indicator: "red",
				message: __(
					"You must scan all approved rolls before submit. Missing scan for: <b>{0}</b>.",
					[pending_items]
				),
			});
			frappe.validated = false;
		}
	},

	process_barcode_scan: function (frm) {
		const barcode = (frm.doc.scan_barcode || frm.doc.custom_barcode_scanner || "").trim();
		if (!barcode || !_is_logistics_material_transfer(frm)) return;
		frm.doc.scan_barcode = "";
		frm.doc.custom_barcode_scanner = "";
		_run_transfer_scan(frm, barcode);
	},
});

frappe.ui.form.on("Stock Entry Detail", {
	qty: function (frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);
		if (
			_is_logistics_material_transfer(frm) &&
			row._protected_qty !== undefined &&
			row.qty !== row._protected_qty
		) {
			frappe.model.set_value(cdt, cdn, "qty", row._protected_qty);
		}
	},
});
