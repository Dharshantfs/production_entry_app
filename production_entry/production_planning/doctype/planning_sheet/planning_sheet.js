const PLANNING_SHEET_DEFAULT_GRID_COLUMNS = [
    'item_code', 'item_name', 'qty', 'uom', 'unit',
    'meter', 'meter_per_roll', 'no_of_rolls', 'weight_per_roll', 'width_inch', 'custom_parent_fabric',
    'length', 'length_per_roll', 'length_roll', 'custom_length', 'custom_length_mtrs',
    'custom_length_per_roll', 'custom_length_roll',
    'gsm', 'quality', 'color', 'custom_quality',
    'planned_date', 'custom_item_planned_date', 'plan_name',
    'custom_plan_code', 'custom_lamination_order_code', 'custom_lamination_order_code_',
    'custom_lam_gsm', 'custom_lam_side', 'custom_lam_side_', 'custom_bopp_gsm',
    'custom_design_code', 'custom_design_name', 'custom_design_colour', 'custom_design_attachment',
    'custom_finishing', 'custom_white_tint', 'custom_no_of_rolls', 'custom_no_of_sheets',
    'total_weight', 'warehouse', 'allocated_to_unit',
    'planned_date', 'custom_movement_type', 'bag_size', 'sheet_size',
];

const PLANNING_SHEET_ALWAYS_VISIBLE_SUFFIXES = ['length', 'planned_date', 'meter', 'roll', 'unit', 'plan_code', 'lamination'];

function ensure_planning_sheet_grid_columns(frm, table) {
    const grid = frm.fields_dict[table] ? frm.fields_dict[table].grid : null;
    if (!grid) return;
    const cdt = grid.doctype;
    let need_refresh = false;

    const touch_df = (df) => {
        if (!df || df.fieldtype === 'Section Break' || df.fieldtype === 'Column Break') return;
        const fn = (df.fieldname || '').toLowerCase();
        const label = (df.label || '').toLowerCase();
        const force_visible = PLANNING_SHEET_DEFAULT_GRID_COLUMNS.includes(df.fieldname)
            || PLANNING_SHEET_ALWAYS_VISIBLE_SUFFIXES.some((s) => fn.includes(s) || label.includes(s));
        if (!force_visible) return;
        if (df.hidden) {
            df.hidden = 0;
            need_refresh = true;
        }
        if (!df.in_list_view) {
            df.in_list_view = 1;
            need_refresh = true;
        }
    };

    for (const fieldname of PLANNING_SHEET_DEFAULT_GRID_COLUMNS) {
        touch_df(frappe.meta.get_docfield(cdt, fieldname, frm.docname));
        const grid_df = (grid.docfields || []).find((d) => d.fieldname === fieldname);
        touch_df(grid_df);
    }
    for (const df of (grid.docfields || [])) {
        touch_df(df);
    }

    if (need_refresh && grid.wrapper && grid.wrapper.is(':visible')) {
        try {
            if (typeof grid.setup_visible_columns === 'function') {
                grid.setup_visible_columns();
            } else if (typeof grid.refresh === 'function') {
                grid.refresh();
            }
        } catch (e) {
            /* grid API differs by Frappe version */
        }
    }
}

frappe.ui.form.on('Planning sheet', {
    refresh: function(frm) {
        ['items', 'planned_items'].forEach((t) => ensure_planning_sheet_grid_columns(frm, t));
        if (!frm.is_new()) {
            frm.add_custom_button(__('Meter to Kgs (All Bag BOM)'), function() {
                frappe.call({
                    method: 'production_entry.production_planning.scheduler_api.convert_meter_to_kgs_for_box_bag_bom',
                    args: { planning_sheet_name: frm.doc.name },
                    freeze: true,
                    callback: function(r) {
                        if (!r.exc) {
                            const msg = r.message || {};
                            frappe.show_alert({
                                message: __('Converted {0} line(s).', [msg.updated || 0]),
                                indicator: 'green',
                            });
                            if (msg.warning) {
                                frappe.msgprint({
                                    title: __('Meter to Kg'),
                                    message: msg.warning,
                                    indicator: 'orange',
                                });
                            }
                            frm.reload_doc();
                        }
                    },
                });
            }, __('Actions'));
            if (typeof register_planning_sheet_stock_check_button === 'function') {
                register_planning_sheet_stock_check_button(frm);
            }
        }
        setTimeout(() => frm.trigger('toggle_221_fields'), 100);
    },

    onload_post_render: function(frm) {
        ['items', 'planned_items'].forEach((t) => ensure_planning_sheet_grid_columns(frm, t));
        setTimeout(() => frm.trigger('toggle_221_fields'), 200);
    },

    validate: function(frm) { frm.trigger('toggle_221_fields'); },
    items_add: function(frm) { setTimeout(() => frm.trigger('toggle_221_fields'), 50); },
    items_remove: function(frm) { setTimeout(() => frm.trigger('toggle_221_fields'), 50); },
    planned_items_add: function(frm) { setTimeout(() => frm.trigger('toggle_221_fields'), 50); },
    planned_items_remove: function(frm) { setTimeout(() => frm.trigger('toggle_221_fields'), 50); },

    toggle_221_fields: function(frm) {
        ['items', 'planned_items'].forEach((table) => ensure_planning_sheet_grid_columns(frm, table));
    },
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
            row.item_code.includes('-211') || row.item_code.startsWith('211') ||
            row.item_code.includes('-212') || row.item_code.startsWith('212') ||
            row.item_code.includes('-213') || row.item_code.startsWith('213') ||
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
            },
        });
    }
}

frappe.ui.form.on('Planning sheet Item', {
    item_code: trigger_toggle,
    custom_design_code: fetch_design_name,
});

frappe.ui.form.on('Planning Table', {
    item_code: trigger_toggle,
    custom_design_code: fetch_design_name,
});
