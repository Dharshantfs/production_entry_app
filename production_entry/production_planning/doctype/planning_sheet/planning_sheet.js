frappe.ui.form.on('Planning sheet', {
    refresh: function(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__('Meter to Kgs (Box Bag BOM)'), function() {
                frappe.call({
                    method: "production_entry.production_planning.scheduler_api.convert_meter_to_kgs_for_box_bag_bom",
                    args: { planning_sheet_name: frm.doc.name },
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
        
        let processes = new Set();
        for (let row of all_items) {
            if (!row.item_code) continue;
            let ic = row.item_code;
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
        
        let required_by = {
            'sheet_size': ['251', '252', '253', '254', '255'],
            'custom_no_of_sheets': ['251', '252', '253', '254', '255'],
            'custom_lam_gsm': ['104', '107', '254', '255', '109', '222', '223', '231', '233', '241', '242'],
            'custom_lam_side': ['104', '107', '254', '255', '109'],
            'custom_lam_side_': ['104', '107', '254', '255', '109'],
            'custom_bopp_gsm': ['107', '255', '109', '222', '223', '231', '233', '241', '242'],
            'custom_cylinder_type': ['107', '255', '109'],
            'custom_white_tint': ['107', '255', '109'],
            'custom_no_of_design_colours': ['107', '255', '109', '222', '223', '231', '233', '241', '242'],
            'custom_bopp_finish_size_mm': ['107', '255', '109'],
            'custom_total_no_of_colours': ['107', '255', '109'],
            'custom_bopp_bom_kgs': ['107', '255', '109'],
            'custom_design_code': ['107', '255', '109', '221', '222', '223', '224', '231', '233', '241', '242'],
            'custom_design_name': ['107', '255', '109', '221', '222', '223', '224', '231', '233', '241', '242'],
            'custom_design_colour': ['107', '255', '109', '221', '222', '223', '224', '231', '233', '241', '242'],
            'custom_design_attachment': ['107', '255', '109', '221', '222', '223', '224', '231', '233', '241', '242'],
            'custom_finishing': ['107', '255', '109', '221', '222', '223', '224', '231', '233', '241', '242'],
            'bag_size': ['221', '222', '223', '224', '231', '233', '241', '242']
        };
        
        ['items', 'planned_items'].forEach(table => {
            let grid = frm.fields_dict[table] ? frm.fields_dict[table].grid : null;
            if (!grid) return;
            
            let cdt = grid.doctype;
            let need_refresh = false;
            
            for (let fieldname of Object.keys(required_by)) {
                let is_required = false;
                if (all_items.length > 0) {
                    for (let p of processes) {
                        if (required_by[fieldname].includes(p)) {
                            is_required = true;
                            break;
                        }
                    }
                }
                
                let is_hidden = 0; // is_required ? 0 : 1; // Temporarily reverted per user request
                
                let df = frappe.meta.get_docfield(cdt, fieldname, frm.docname);
                if (df && !!df.hidden != !!is_hidden) {
                    df.hidden = is_hidden;
                    need_refresh = true;
                }
                
                if (grid.docfields) {
                    let grid_df = grid.docfields.find(d => d.fieldname === fieldname);
                    if (grid_df && !!grid_df.hidden != !!is_hidden) {
                        grid_df.hidden = is_hidden;
                        need_refresh = true;
                    }
                }
            }
            
            if (need_refresh) {
                if (grid.wrapper && grid.wrapper.is(':visible')) {
                    grid.setup_columns();
                    grid.refresh();
                } else {
                    // If grid is not visible (e.g. in another tab or loading),
                    // we don't call setup_columns() because it calculates 0 width and collapses them!
                    // Frappe will automatically setup columns when the grid becomes visible.
                }
            }
        });
    }
});

function trigger_toggle(frm, cdt, cdn) {
    frm.trigger('toggle_221_fields');
    if (cdt && cdn) {
        let row = frappe.get_doc(cdt, cdn);
        if (row.item_code && (
            row.item_code.includes('-221') || row.item_code.startsWith('221') ||
            row.item_code.includes('-224') || row.item_code.startsWith('224') ||
            row.item_code.includes('-222') || row.item_code.startsWith('222') ||
            row.item_code.includes('-223') || row.item_code.startsWith('223') ||
            row.item_code.includes('-231') || row.item_code.startsWith('231') ||
            row.item_code.includes('-233') || row.item_code.startsWith('233') ||
            row.item_code.includes('-241') || row.item_code.startsWith('241') ||
            row.item_code.includes('-242') || row.item_code.startsWith('242')
        )) {
            let parts = row.item_code.split('-');
            if (parts.length > 1) {
                let dc = parts[0];
                if (row.custom_design_code !== dc) {
                    frappe.model.set_value(cdt, cdn, 'custom_design_code', dc);
                } else {
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