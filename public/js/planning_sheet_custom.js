// Planning Sheet Custom Script - Display customer name instead of ID

const process_fields_map = {
    '100': [
        'item_code', 'item_name', 'qty', 'uom', 'quality', 'color', 
        'gsm', 'meter', 'meter_per_roll', 'no_of_rolls', 'unit', 
        'order_sheet', 'spr_name', 'work_order'
    ],
    '104': [],
    '105': []
};

const core_fields = new Set(['item_code', 'item_name', 'qty', 'uom', 'unit']);

function apply_process_code_visibility(frm) {
    let active_process_codes = new Set();
    
    (frm.doc.items || []).forEach(row => {
        if (row.item_code && row.item_code.length >= 3) {
            active_process_codes.add(row.item_code.substring(0, 3));
        }
    });
    (frm.doc.planned_items || []).forEach(row => {
        if (row.item_code && row.item_code.length >= 3) {
            active_process_codes.add(row.item_code.substring(0, 3));
        }
    });

    let fields_to_show = new Set();
    active_process_codes.forEach(code => {
        if (process_fields_map[code]) {
            process_fields_map[code].forEach(f => fields_to_show.add(f));
        }
    });

    ['items', 'planned_items'].forEach(table_fieldname => {
        let grid = frm.fields_dict[table_fieldname] && frm.fields_dict[table_fieldname].grid;
        if (!grid) return;
        
        grid.docfields.forEach(df => {
            if (!core_fields.has(df.fieldname)) {
                let is_hidden = fields_to_show.has(df.fieldname) ? 0 : 1;
                grid.update_docfield_property(df.fieldname, 'hidden', is_hidden);
            }
        });
    });
}

// Keep legacy `items` and board `planned_items` unit fields in sync when `source_item` links rows
// (avoids stale board grid until full reload).
frappe.ui.form.on('Planning sheet Item', {
    item_code: function(frm) {
        apply_process_code_visibility(frm);
    },
    unit: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        const psi = (row.name || '').trim();
        if (!psi || !frm.doc.planned_items || !frm.doc.planned_items.length) return;
        (frm.doc.planned_items || []).forEach((pr) => {
            if ((pr.source_item || '').trim() === psi) {
                frappe.model.set_value(pr.doctype, pr.name, 'unit', row.unit);
            }
        });
        frm.refresh_field('planned_items');
                        frm.trigger('toggle_221_fields');
    },
});

frappe.ui.form.on('Planning Table', {
    item_code: function(frm) {
        apply_process_code_visibility(frm);
    },
    unit: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        const si = (row.source_item || '').trim();
        if (!si || !frm.doc.items || !frm.doc.items.length) return;
        (frm.doc.items || []).forEach((it) => {
            if ((it.name || '').trim() === si) {
                frappe.model.set_value(it.doctype, it.name, 'unit', row.unit);
            }
        });
        frm.refresh_field('items');
    },
});

frappe.ui.form.on('Planning sheet', {
    refresh: function(frm) {
        if (!frm.doc || !frm.doc.name) return;
        apply_process_code_visibility(frm);
        frm.add_custom_button(__('Update Colors'), function() {
            frappe.call({
                method: 'production_entry.production_planning.scheduler_api.refresh_planning_sheet_colors',
                args: { planning_sheet: frm.doc.name },
                freeze: true,
                freeze_message: __('Updating colors from Sales Order...'),
                callback: function(r) {
                    const m = r.message || {};
                    frappe.show_alert({
                        message: __(m.message || 'Color update completed.'),
                        indicator: 'green'
                    });
                    frm.reload_doc();
                }
            });
        }, __('Actions'));
        frm.add_custom_button(__('Update SPR + Order Sheet'), function() {
            frappe.call({
                method: 'production_entry.production_planning.scheduler_api.refresh_planning_sheet_spr_and_order_sheet',
                args: { planning_sheet: frm.doc.name },
                freeze: true,
                freeze_message: __('Updating SPR and Order Sheet links...'),
                callback: function(r) {
                    const m = r.message || {};
                    frappe.show_alert({
                        message: __(m.message || 'SPR/Order Sheet update completed.'),
                        indicator: 'green'
                    });
                    frm.reload_doc();
                }
            });
        }, __('Actions'));
        frm.add_custom_button(__('Manual Update SPR/Order Sheet'), function() {
            const d = new frappe.ui.Dialog({
                title: __('Manual Update SPR / Order Sheet'),
                fields: [
                    {
                        fieldname: 'help',
                        fieldtype: 'HTML',
                        options:
                            '<p class="text-muted small">' +
                            __('Paste one line: row_name OR item_code,order_sheet,spr_name') +
                            '<br>' +
                            __('Example: 1001001...,MFG-PP-2026-00354,SPR-2026-00180') +
                            '</p>',
                    },
                    { fieldname: 'lines', fieldtype: 'Long Text', reqd: 1, label: __('Mappings') },
                ],
                primary_action_label: __('Apply'),
                primary_action: function(vals) {
                    const text = (vals.lines || '').trim();
                    if (!text) return;
                    const mappings = text
                        .split(/\r?\n/)
                        .map((ln) => ln.trim())
                        .filter(Boolean)
                        .map((ln) => {
                            const p = ln.split(',').map((x) => (x || '').trim());
                            const first = p[0] || '';
                            const looksLikeRow = /^PT-|^new-|^ROW-|^PTROW/i.test(first);
                            return {
                                row_name: looksLikeRow ? first : '',
                                item_code: looksLikeRow ? '' : first,
                                order_sheet: p[1] || '',
                                spr_name: p[2] || '',
                            };
                        });
                    frappe.call({
                        method: 'production_entry.production_planning.scheduler_api.manual_update_planning_sheet_links',
                        args: { planning_sheet: frm.doc.name, mappings: JSON.stringify(mappings) },
                        freeze: true,
                        freeze_message: __('Applying manual mapping...'),
                        callback: function(r) {
                            const m = r.message || {};
                            d.hide();
                            if (m.errors && m.errors.length) {
                                frappe.msgprint({
                                    title: __('Manual Update Completed with Errors'),
                                    message: (m.message || '') + '<br><br>' + m.errors.map((e) => frappe.utils.escape_html(e)).join('<br>'),
                                });
                            } else {
                                frappe.show_alert({ message: __(m.message || 'Updated successfully'), indicator: 'green' });
                            }
                            frm.reload_doc();
                        },
                    });
                },
            });
            d.show();
        }, __('Actions'));
    },

    items_add: function(frm) { apply_process_code_visibility(frm); },
    items_remove: function(frm) { apply_process_code_visibility(frm); },
    planned_items_add: function(frm) { apply_process_code_visibility(frm); },
    planned_items_remove: function(frm) { apply_process_code_visibility(frm); },

    after_load: function(frm) {
        // Fetch and display customer name
        if (frm.doc.customer) {
            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'Customer',
                    filters: { name: frm.doc.customer },
                    fieldname: ['customer_name']
                },
                callback: function(r) {
                    if (r.message) {
                        const customerName = r.message.customer_name || frm.doc.customer;
                        // Update the customer field display in the form
                        frm.set_df_property('customer', 'label', `Customer (${frm.doc.customer}): ${customerName}`);
                        // Also add visual indicator
                        frm.refresh_field('customer');
                    }
                }
            });
        }
    },
    
    customer: function(frm) {
        // When customer changes, update the display label
        if (frm.doc.customer) {
            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'Customer',
                    filters: { name: frm.doc.customer },
                    fieldname: ['customer_name']
                },
                callback: function(r) {
                    if (r.message) {
                        const customerName = r.message.customer_name || frm.doc.customer;
                        frm.set_df_property('customer', 'label', `Customer (${frm.doc.customer}): ${customerName}`);
                        frm.refresh_field('customer');
                    }
                }
            });
        }
    }
});
