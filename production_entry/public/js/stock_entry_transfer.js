// Transfer STE: show destination company on Party when set from Transfer Approval.
frappe.ui.form.on("Stock Entry", {
	refresh(frm) {
		const co = (frm.doc.custom_transfer_to_company || "").trim();
		if (!co) return;
		if (frm.fields_dict.party_type && !frm.doc.party_type) {
			frm.set_value("party_type", "Company");
		}
		if (frm.fields_dict.party && !frm.doc.party) {
			frm.set_value("party", co);
		}
	},
});


frappe.ui.form.on("Stock Entry", {
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
        
        if (!expected_item) {
            frappe.msgprint({title: __('Error'), indicator: 'red', message: __('Cannot determine expected item. Please add at least one row first.')});
            return;
        }
        
        // First check if the scanned batch is already in the table
        let existing_row = (frm.doc.items || []).find(r => r.batch_no === barcode || r.custom_roll_no === barcode);
        if (existing_row) {
            // Check if the item matches (just in case)
            if (existing_row.item_code !== expected_item) {
                frappe.msgprint({title: __('Wrong Item'), indicator: 'red', message: `The scanned batch belongs to <b>${existing_row.item_code}</b>, but we are transferring <b>${expected_item}</b>.`});
                frappe.utils.play_sound("error");
                return;
            }
            
            frappe.model.set_value(existing_row.doctype, existing_row.name, 'custom_scanned_qty', existing_row.qty);
            frappe.show_alert({message: `Scanned: ${barcode}`, indicator: 'green'});
            frappe.utils.play_sound("submit");
            return;
        }
        
        // If not in the table, we need to fetch the batch item from the database
        let source_warehouse = frm.doc.from_warehouse || (frm.doc.items && frm.doc.items[0].s_warehouse) || '';
        
        frappe.call({
            method: 'production_entry.production_planning.scheduler_api.scan_stock_entry_batch',
            args: {
                barcode: barcode,
                expected_item: expected_item,
                source_warehouse: source_warehouse
            },
            callback: function(r) {
                if (r.message && !r.message.error) {
                    let batch = r.message;
                    if (batch.available_qty <= 0) {
                        frappe.msgprint({title: __('No Stock'), indicator: 'orange', message: `The scanned batch (${barcode}) has 0 qty in the source warehouse.`});
                        frappe.utils.play_sound("error");
                        return;
                    }
                    
                    // Add new row
                    let new_row = frm.add_child("items");
                    new_row.item_code = batch.item_code;
                    new_row.s_warehouse = frm.doc.from_warehouse || (frm.doc.items && frm.doc.items[0].s_warehouse) || '';
                    new_row.t_warehouse = frm.doc.to_warehouse || (frm.doc.items && frm.doc.items[0].t_warehouse) || '';
                    new_row.qty = batch.available_qty;
                    new_row.uom = frm.doc.items[0].uom || 'Kg';
                    new_row.stock_uom = frm.doc.items[0].stock_uom || 'Kg';
                    new_row.conversion_factor = 1;
                    new_row.batch_no = batch.batch_no;
                    new_row.custom_scanned_qty = batch.available_qty;
                    // Optionally custom_roll_no if it exists
                    if (frappe.meta.has_field(new_row.doctype, 'custom_roll_no')) {
                        new_row.custom_roll_no = batch.batch_no;
                    }
                    
                    frm.refresh_field("items");
                    frappe.show_alert({message: `Added & Scanned: ${barcode}`, indicator: 'green'});
                    frappe.utils.play_sound("submit");
                } else if (r.message && r.message.error) {
                    frappe.msgprint({title: __('Scan Failed'), indicator: 'red', message: r.message.error});
                    frappe.utils.play_sound("error");
                }
            }
        });
    }
});
