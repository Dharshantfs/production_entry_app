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
        
        frm.trigger('toggle_221_fields');
    },
    
    toggle_221_fields: function(frm) {
        let is_221 = false;
        
        let all_items = (frm.doc.items || []).concat(frm.doc.planned_items || []);
        for (let row of all_items) {
            if (row.item_code && (row.item_code.includes('-221') || row.item_code.startsWith('221'))) {
                is_221 = true;
                break;
            }
        }
        
        let fields_to_hide = [
            'sheet_size',
            'custom_lam_side',
            'custom_lam_side_',
            'custom_lam_gsm',
            'custom_bopp_gsm',
            'custom_cylinder_type',
            'custom_white_tint',
            'custom_no_of_design_colours',
            'custom_finishing',
            'custom_total_no_of_colours',
            'custom_bopp_bom_kgs',
            'custom_no_of_sheets'
        ];
        
        ['items', 'planned_items'].forEach(table => {
            if (frm.fields_dict[table] && frm.fields_dict[table].grid) {
                fields_to_hide.forEach(fieldname => {
                    let df = frappe.meta.get_docfield(frm.fields_dict[table].grid.doctype, fieldname, frm.docname);
                    if (df) {
                        frm.fields_dict[table].grid.update_docfield_property(fieldname, 'hidden', is_221 ? 1 : 0);
                    }
                });
            }
        });
    }
});

function trigger_toggle(frm) {
    frm.trigger('toggle_221_fields');
}

frappe.ui.form.on('Planning sheet Item', {
    item_code: trigger_toggle
});

frappe.ui.form.on('Planning Table', {
    item_code: trigger_toggle
});
