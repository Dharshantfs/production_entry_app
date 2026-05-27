frappe.ui.form.on('Planning sheet', {
    refresh: function(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__('Meter to Kgs (Box Bag BOM)'), function() {
                frappe.call({
                    method: "production_entry.production_planning.scheduler_api.convert_meter_to_kgs_for_box_bag_bom",
                    args: {
                        planning_sheet_name: frm.doc.name
                    },
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.msgprint(__('Converted ' + (r.message.updated || 0) + ' items from Meter to Kgs successfully.'));
                            frm.reload_doc();
                        }
                    }
                });
            }, __('Actions'));
        }
        setTimeout(() => frm.trigger('toggle_221_fields'), 100);
    },
    
    onload_post_render: function(frm) { setTimeout(() => frm.trigger('toggle_221_fields'), 200); },
    
    validate: function(frm) { frm.trigger('toggle_221_fields'); },
    items_add: function(frm) { setTimeout(() => frm.trigger('toggle_221_fields'), 50); },
    items_remove: function(frm) { setTimeout(() => frm.trigger('toggle_221_fields'), 50); },
    planned_items_add: function(frm) { setTimeout(() => frm.trigger('toggle_221_fields'), 50); },
    planned_items_remove: function(frm) { setTimeout(() => frm.trigger('toggle_221_fields'), 50); },
    
    toggle_221_fields: function(frm) {
        let all_items = (frm.doc.items || []).concat(frm.doc.planned_items || []);
        if (all_items.length === 0) return;
        
        let processes = new Set();
        
        for (let row of all_items) {
            if (!row.item_code) continue;
            let ic = row.item_code;
            
            // Extract process code (e.g. 100, 102, 103, 104, 107, 251, 221)
            let process_code = "";
            if (ic.includes('-')) {
                let parts = ic.split('-');
                for (let seg of parts) {
                    let nums = seg.replace(/[^0-9]/g, '');
                    if (nums.length >= 3) {
                        process_code = nums.substring(0, 3);
                        break;
                    }
                }
            } else {
                let nums = ic.replace(/[^0-9]/g, '');
                if (nums.length >= 3) {
                    process_code = nums.substring(0, 3);
                }
            }
            if (process_code) processes.add(process_code);
        }
        
        // Positive mapping: A field is visible if ANY of the processes in the grid requires it
        let required_by = {
            'sheet_size': ['251', '252', '253', '254', '255'],
            'custom_no_of_sheets': ['251', '252', '253', '254', '255'],
            
            'custom_lam_gsm': ['104', '107', '254', '255', '109'],
            'custom_lam_side': ['104', '107', '254', '255', '109'],
            'custom_lam_side_': ['104', '107', '254', '255', '109'],
            
            'custom_bopp_gsm': ['107', '255', '109'],
            'custom_cylinder_type': ['107', '255', '109'],
            'custom_white_tint': ['107', '255', '109'],
            'custom_no_of_design_colours': ['107', '255', '109'],
            'custom_bopp_finish_size_mm': ['107', '255', '109'],
            'custom_total_no_of_colours': ['107', '255', '109'],
            'custom_bopp_bom_kgs': ['107', '255', '109'],
            
            'custom_design_code': ['107', '255', '109', '221'],
            'custom_design_name': ['107', '255', '109', '221'],
            'custom_design_colour': ['107', '255', '109', '221'],
            'custom_design_attachment': ['107', '255', '109', '221'],
            
            'custom_finishing': ['107', '255', '109', '221'],
            'bag_size': ['221']
        };
        
        let fields_to_toggle = Object.keys(required_by);
        
        ['items', 'planned_items'].forEach(table => {
            if (frm.fields_dict[table] && frm.fields_dict[table].grid) {
                let updated = false;
                
                for (let fieldname of fields_to_toggle) {
                    let df = frappe.meta.get_docfield(frm.fields_dict[table].grid.doctype, fieldname, frm.docname);
                    if (df) {
                        let is_required = false;
                        for (let p of processes) {
                            if (required_by[fieldname].includes(p)) {
                                is_required = true;
                                break;
                            }
                        }
                        
                        frm.fields_dict[table].grid.update_docfield_property(fieldname, 'hidden', is_required ? 0 : 1);
                        updated = true;
                    }
                }
                
                if (updated) {
                    frm.fields_dict[table].grid.refresh();
                }
            }
        });
    }
});

function trigger_toggle(frm, cdt, cdn) {
    frm.trigger('toggle_221_fields');
    if (cdt && cdn) {
        let row = frappe.get_doc(cdt, cdn);
        if (row.item_code && (row.item_code.includes('-221') || row.item_code.startsWith('221'))) {
            let parts = row.item_code.split('-');
            if (parts.length > 1) {
                let dc = parts[0];
                if (row.custom_design_code !== dc) {
                    frappe.model.set_value(cdt, cdn, 'custom_design_code', dc);
                } else {
                    // Trigger fetch manually if already set
                    fetch_design_name(frm, cdt, cdn);
                }
            }
        }
    }
}

function fetch_design_name(frm, cdt, cdn) {
    let row = frappe.get_doc(cdt, cdn);
    if (row.custom_design_code) {
        frappe.call({
            method: 'production_entry.production_planning.scheduler_api._design_master_extra_fields',
            args: { design_code: row.custom_design_code },
            callback: function(r) {
                if (r.message && r.message.custom_design_name) {
                    frappe.model.set_value(cdt, cdn, 'custom_design_name', r.message.custom_design_name);
                }
            }
        });
    }
}

frappe.ui.form.on('Planning sheet Item', {
    item_code: trigger_toggle,
    custom_design_code: fetch_design_name
});

frappe.ui.form.on('Planning Table', {
    item_code: trigger_toggle,
    custom_design_code: fetch_design_name
});
