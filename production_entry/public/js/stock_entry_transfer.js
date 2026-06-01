// Transfer STE: show destination company on Party when set from Transfer Approval.
frappe.ui.form.on("Stock Entry", {
	onload(frm) {
		// Handled in refresh now
	},

	refresh(frm) {
		// Forcefully hijack the barcode events so standard ERPNext scanner never runs!
		if (frm.script_manager && frm.script_manager.events) {
			if (frm.script_manager.events.scan_barcode) {
				frm.script_manager.events.scan_barcode = [ function(frm) { frm.trigger('process_barcode_scan'); } ];
			}
			if (frm.script_manager.events.custom_barcode_scanner) {
				frm.script_manager.events.custom_barcode_scanner = [ function(frm) { frm.trigger('process_barcode_scan'); } ];
			}
		}
		
		// If barcode scanner component exists, silence it
		if (frm.barcode_scanner) {
			frm.barcode_scanner.process_scan = function() {};
			frm.barcode_scanner.clean_up = function() {};
		}

		const co = (frm.doc.custom_transfer_to_company || "").trim();
		if (co) {
			if (frm.fields_dict.party_type && !frm.doc.party_type) {
				frm.set_value("party_type", "Company");
			}
			if (frm.fields_dict.party && !frm.doc.party) {
				frm.set_value("party", co);
			}
		}

		if (frm.doc.docstatus === 0 && frm.doc.stock_entry_type === "Material Transfer" && frm.doc.items && frm.doc.items.length > 0) {
			frm.add_custom_button(__('Approved Rolls'), () => {
				frappe.call({
					method: 'frappe.client.get_list',
					args: {
						doctype: 'Transfer Approval',
						filters: { stock_entry: frm.doc.name },
						fields: ['name']
					},
					callback: function(r) {
						if(r.message && r.message.length > 0) {
							let ta_name = r.message[0].name;
							frappe.call({
								method: 'frappe.client.get',
								args: { doctype: 'Transfer Approval', name: ta_name },
								callback: function(r2) {
									if(r2.message) {
										let grouped = {};
										(r2.message.lines || []).forEach(row => {
											if (!grouped[row.item_code]) grouped[row.item_code] = [];
											grouped[row.item_code].push(row);
										});
										let html = "";
										for (let ic in grouped) {
											html += `<h4>${ic}</h4>`;
											html += "<table class='table table-bordered'><tr><th>Batch No</th><th>Qty</th></tr>";
											grouped[ic].forEach(row => {
												html += `<tr><td>${row.batch_no || ''}</td><td>${row.qty}</td></tr>`;
											});
											html += "</table><br>";
										}
										let d = new frappe.ui.Dialog({
											title: 'Approved Rolls',
											fields: [{fieldtype: 'HTML', fieldname: 'html_content', options: html}]
										});
										d.show();
									}
								}
							});
						} else {
							frappe.msgprint("No Transfer Approval linked to this Stock Entry.");
						}
					}
				});
			}, __('Actions'));
		}
	},

	validate(frm) {
		if (frm.doc.stock_entry_type === "Material Transfer" && frm.doc.items) {
			let pending = frm.doc.items.filter(r => (r.qty || 0) > ((r.scanned_qty || r.custom_scanned_qty) || 0) + 0.01);
			if (pending.length > 0) {
				let pending_items = pending.map(r => r.item_code).join(', ');
				frappe.msgprint({title: "Validation Error", indicator: "red", message: `You must scan all approved rolls! Missing scanned quantity for: <b>${pending_items}</b>.`});
				frappe.validated = false;
			}
		}
	},

    process_barcode_scan: function(frm) {
        let barcode = (frm.doc.scan_barcode || frm.doc.custom_barcode_scanner || "").trim();
        if (!barcode) return;
        
        // Immediately clear the barcode field to allow scanning the next one
        if (frm.doc.scan_barcode) frappe.model.set_value(frm.doctype, frm.docname, 'scan_barcode', '');
        if (frm.doc.custom_barcode_scanner) frappe.model.set_value(frm.doctype, frm.docname, 'custom_barcode_scanner', '');
        
        let expected_item = null;
        if (frm.doc.items && frm.doc.items.length > 0) {
            expected_item = frm.doc.items[0].item_code;
        }
        
        // STRICT INDIVIDUAL ROW LOGIC - No Grouping
        let existing_row = (frm.doc.items || []).find(r => r.batch_no === barcode || r.custom_roll_no === barcode);
        
        if (existing_row) {
            if (expected_item && existing_row.item_code !== expected_item) {
                frappe.msgprint({title: __('Wrong Item'), indicator: 'red', message: `The scanned batch belongs to <b>${existing_row.item_code}</b>, but we are transferring <b>${expected_item}</b>.`});
                frappe.utils.play_sound("error");
                return;
            }
            
            existing_row._protected_qty = existing_row.qty;
            
            let updates = { custom_scanned_qty: existing_row.qty };
            if (frappe.meta.has_field(existing_row.doctype, 'scanned_qty')) {
                updates.scanned_qty = existing_row.qty;
            }
            
            frappe.model.set_value(existing_row.doctype, existing_row.name, updates).then(() => {
                frm.refresh_field("items");
                frappe.show_alert({message: `Verified: <b>${barcode}</b>`, indicator: 'green'});
                frappe.utils.play_sound("submit");
                setTimeout(() => { existing_row._protected_qty = undefined; }, 3000);
            });
            return;
        } else {
            // Batch was not found in the prepopulated list!
            frappe.msgprint({
                title: __('Batch Not Found'), 
                indicator: 'orange', 
                message: `The scanned batch <b>${barcode}</b> is not in the list! Please make sure it was populated correctly.`
            });
            frappe.utils.play_sound("error");
        }
    }
});

// INTERCEPTOR: Catch the background script trying to change the Qty and block it!
frappe.ui.form.on('Stock Entry Detail', {
    qty: function(frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);
        
        // If the row is currently locked and the background script changed the qty, revert it instantly
        if (row._protected_qty !== undefined && row.qty !== row._protected_qty) {
            frappe.model.set_value(cdt, cdn, 'qty', row._protected_qty);
        }
    }
});
