// Transfer STE: show destination company on Party when set from Transfer Approval.
frappe.ui.form.on("Stock Entry", {
	onload(frm) {
		// Handled in refresh now
	},

	refresh(frm) {
		// Completely remove the standard ERPNext scan_barcode event handler so it doesn't add rows!
		if (frm.script_manager && frm.script_manager.events && frm.script_manager.events.scan_barcode) {
			frm.script_manager.events.scan_barcode = frm.script_manager.events.scan_barcode.filter(
				fn => fn.toString().includes('process_barcode_scan')
			);
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

    scan_barcode: function(frm) { frm.trigger('process_barcode_scan'); },
    custom_barcode_scanner: function(frm) { frm.trigger('process_barcode_scan'); },
    
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
        
        // First check if the scanned batch is already in the table using old multi-row logic (fallback)
        let existing_row = (frm.doc.items || []).find(r => r.batch_no === barcode || r.custom_roll_no === barcode);
        if (existing_row) {
            if (expected_item && existing_row.item_code !== expected_item) {
                frappe.msgprint({title: __('Wrong Item'), indicator: 'red', message: `The scanned batch belongs to <b>${existing_row.item_code}</b>, but we are transferring <b>${expected_item}</b>.`});
                frappe.utils.play_sound("error");
                return;
            }
            
            existing_row._protected_qty = existing_row.qty;
            frappe.model.set_value(existing_row.doctype, existing_row.name, 'custom_scanned_qty', existing_row.qty);
            if (frappe.meta.has_field(existing_row.doctype, 'scanned_qty')) {
                frappe.model.set_value(existing_row.doctype, existing_row.name, 'scanned_qty', existing_row.qty);
            }
            
            frappe.show_alert({message: `Verified: <b>${barcode}</b>`, indicator: 'green'});
            frappe.utils.play_sound("submit");
            setTimeout(() => { existing_row._protected_qty = undefined; }, 3000);
            return;
        }
        
        let source_warehouse = frm.doc.from_warehouse || (frm.doc.items && frm.doc.items.length > 0 ? frm.doc.items[0].s_warehouse : '');
        
        frappe.call({
            method: 'production_entry.production_planning.scheduler_api.scan_stock_entry_batch',
            args: { barcode: barcode, expected_item: expected_item, source_warehouse: source_warehouse },
            callback: function(r) {
                if (r.message && !r.message.error) {
                    let batch = r.message;

                    if (expected_item && batch.item_code && batch.item_code !== expected_item) {
                        frappe.msgprint({ title: __('Wrong Item'), indicator: 'red', message: `The scanned batch <b>${barcode}</b> belongs to item <b>${batch.item_code}</b>, but this transfer is for <b>${expected_item}</b>. Roll NOT added.` });
                        frappe.utils.play_sound("error");
                        return;
                    }

                    if (batch.available_qty <= 0) {
                        frappe.msgprint({title: __('No Stock'), indicator: 'orange', message: `The scanned batch (${barcode}) has 0 qty in the source warehouse.`});
                        frappe.utils.play_sound("error");
                        return;
                    }
                    
                    let summary_row = (frm.doc.items || []).find(r => r.item_code === batch.item_code);
                    if (!summary_row) {
                        frappe.msgprint({title: __('Row not found'), indicator: 'red', message: `No item row found for <b>${batch.item_code}</b> in the table.`});
                        frappe.utils.play_sound("error");
                        return;
                    }
                    
                    frappe.call({
                        method: 'production_entry.production_planning.scheduler_api.add_batch_to_bundle',
                        args: {
                            bundle_id: summary_row.serial_and_batch_bundle || null,
                            item_code: batch.item_code,
                            warehouse: source_warehouse || summary_row.s_warehouse,
                            batch_no: batch.batch_no,
                            qty: batch.available_qty
                        },
                        callback: function(br) {
                            if (br.message) {
                                let res = br.message;
                                if (!res.added) {
                                    frappe.msgprint({title: __('Already Scanned'), indicator: 'orange', message: `Roll <b>${barcode}</b> is already in the list for this item.`});
                                    frappe.utils.play_sound("error");
                                    return;
                                }
                                
                                let new_scanned_qty = (summary_row.scanned_qty || summary_row.custom_scanned_qty || 0) + res.qty_added;
                                
                                let updates = {
                                    serial_and_batch_bundle: res.bundle_id,
                                    custom_scanned_qty: new_scanned_qty
                                };
                                if (frappe.meta.has_field(summary_row.doctype, 'scanned_qty')) {
                                    updates.scanned_qty = new_scanned_qty;
                                }
                                
                                summary_row._protected_qty = summary_row.qty; // Lock qty against background refresh
                                frappe.model.set_value(summary_row.doctype, summary_row.name, updates).then(() => {
                                    frm.refresh_field("items");
                                    frappe.show_alert({message: `Added & Scanned: ${barcode}`, indicator: 'green'});
                                    frappe.utils.play_sound("submit");
                                    setTimeout(() => { summary_row._protected_qty = undefined; }, 3000);
                                });
                            }
                        }
                    });
                } else if (r.message && r.message.error) {
                    frappe.msgprint({title: __('Scan Failed'), indicator: 'red', message: r.message.error});
                    frappe.utils.play_sound("error");
                }
            }
        });
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
