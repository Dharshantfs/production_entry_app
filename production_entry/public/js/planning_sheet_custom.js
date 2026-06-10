// Planning Sheet Custom Script - Display customer name instead of ID

/** Hidden from grid by default; user can enable via Configure Columns. */
const PS_GRID_DEFAULT_HIDDEN = {
    so_item: 1,
    sales_order_item: 1,
    custom_transfer_destination: 1,
    custom_transfer_status: 1,
    custom_slitting_shift: 1,
    custom_lamination_shift: 1,
    custom_sheet_cutting_shift: 1,
    custom_printing_shift: 1,
    allocated_to_unit: 1,
};

const PS_GRID_META_BY_FIELD = {
    items: 'Planning sheet Item',
    planned_items: 'Planning Table',
};

function ps_get_grid_columns_module() {
    try {
        if (typeof production_entry !== 'undefined' && production_entry.grid_columns) {
            return production_entry.grid_columns;
        }
        if (typeof window !== 'undefined' && window.production_entry && window.production_entry.grid_columns) {
            return window.production_entry.grid_columns;
        }
    } catch (e) {
        /* ignore */
    }
    return null;
}

function ps_build_grid_show_fields(metaDoctype) {
    const skipNames = PS_GRID_DEFAULT_HIDDEN;
    const skipTypes = { 'Column Break': 1, 'Section Break': 1, 'Tab Break': 1, 'HTML': 1 };
    const names = [];
    const seen = {};
    function pushField(fn) {
        if (!fn || seen[fn] || skipNames[fn]) {
            return;
        }
        const df = frappe.meta.get_docfield(metaDoctype, fn);
        if (!df || skipTypes[df.fieldtype] || cint(df.hidden)) {
            return;
        }
        seen[fn] = 1;
        names.push(fn);
    }
    const meta = frappe.get_meta(metaDoctype);
    const fo = meta && meta.field_order;
    if (Array.isArray(fo) && fo.length) {
        fo.forEach(pushField);
    } else {
        (frappe.meta.get_docfields(metaDoctype) || []).forEach(function (df) {
            pushField(df && df.fieldname);
        });
    }
    return names;
}

function ps_realign_planning_grids(frm) {
    const gc = ps_get_grid_columns_module();
    if (!gc) {
        return;
    }
    Object.keys(PS_GRID_META_BY_FIELD).forEach(function (tableField) {
        if (typeof gc.realign === 'function') {
            gc.realign(frm, tableField);
        }
        if (typeof gc.sync_header_scroll === 'function') {
            gc.sync_header_scroll(frm, tableField);
        }
    });
}

function ps_apply_planning_grid_columns(frm) {
    if (!frm || !frm.fields_dict) {
        return;
    }
    const gc = ps_get_grid_columns_module();
    if (!gc || typeof gc.apply !== 'function') {
        return;
    }
    Object.keys(PS_GRID_META_BY_FIELD).forEach(function (tableField) {
        const metaDoctype = PS_GRID_META_BY_FIELD[tableField];
        const show = ps_build_grid_show_fields(metaDoctype);
        if (show.length) {
            gc.apply(frm, tableField, metaDoctype, show);
        }
    });
    ps_realign_planning_grids(frm);
}

function ps_schedule_planning_grid_columns(frm) {
    if (!frm || frm.is_new()) {
        return;
    }
    const gc = ps_get_grid_columns_module();
    const run = function () {
        ps_apply_planning_grid_columns(frm);
        setTimeout(function () {
            ps_realign_planning_grids(frm);
        }, 120);
    };
    if (!gc || typeof gc.debounce !== 'function') {
        run();
        return;
    }
    gc.debounce(frm, 'ps_grid_columns', run, 150);
}

// Keep legacy `items` and board `planned_items` unit fields in sync when `source_item` links rows
// (avoids stale board grid until full reload).
function _norm(v) {
    return String(v || "").trim();
}

function _rowSoKey(row) {
    // Planning sheet Item uses `so_item`; board rows can be `so_item` or `sales_order_item`
    return _norm(row?.so_item || row?.sales_order_item || row?.salesOrderItem);
}

function _rowItemCode(row) {
    return _norm(row?.item_code || row?.itemCode);
}

function _findPlannedRowForLegacy(frm, legacyRow) {
    const psi = _norm(legacyRow?.name);
    const soKey = _rowSoKey(legacyRow);
    const ic = _rowItemCode(legacyRow);
    const planned = frm?.doc?.planned_items || [];
    if (!planned.length) return null;

    // 1) strict link: board.source_item == legacy.name
    if (psi) {
        const hit = planned.find((pr) => _norm(pr.source_item) === psi);
        if (hit) return hit;
    }
    // 2) fallback: match by SO line + item_code
    if (soKey && ic) {
        const hit2 = planned.find((pr) => _rowSoKey(pr) === soKey && _rowItemCode(pr) === ic);
        if (hit2) return hit2;
    }
    return null;
}

function _findLegacyRowForPlanned(frm, plannedRow) {
    const si = _norm(plannedRow?.source_item);
    const soKey = _rowSoKey(plannedRow);
    const ic = _rowItemCode(plannedRow);
    const legacy = frm?.doc?.items || [];
    if (!legacy.length) return null;

    // 1) strict link: legacy.name == board.source_item
    if (si) {
        const hit = legacy.find((it) => _norm(it.name) === si);
        if (hit) return hit;
    }
    // 2) fallback: match by SO line + item_code
    if (soKey && ic) {
        const hit2 = legacy.find((it) => _rowSoKey(it) === soKey && _rowItemCode(it) === ic);
        if (hit2) return hit2;
    }
    return null;
}

frappe.ui.form.on('Planning sheet Item', {
    unit: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        const pr = _findPlannedRowForLegacy(frm, row);
        if (!pr) return;
        frappe.model.set_value(pr.doctype, pr.name, 'unit', row.unit);
        if (row.custom_plan_code) {
            frappe.model.set_value(pr.doctype, pr.name, 'custom_plan_code', row.custom_plan_code);
        }
        if (row.plan_name) {
            frappe.model.set_value(pr.doctype, pr.name, 'plan_name', row.plan_name);
        }
        frm.refresh_field('planned_items');
        ps_schedule_planning_grid_columns(frm);
        setTimeout(function () {
            registerWorkingSheetCuttingChangeBomButton(frm);
        }, 100);
    },
    custom_plan_code: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        const pr = _findPlannedRowForLegacy(frm, row);
        if (!pr) return;
        if (row.custom_plan_code) {
            frappe.model.set_value(pr.doctype, pr.name, 'custom_plan_code', row.custom_plan_code);
        }
        if (row.plan_name) {
            frappe.model.set_value(pr.doctype, pr.name, 'plan_name', row.plan_name);
        }
        frm.refresh_field('planned_items');
        ps_schedule_planning_grid_columns(frm);
    },
});

frappe.ui.form.on('Planning Table', {
    unit: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        const leg = _findLegacyRowForPlanned(frm, row);
        if (!leg) return;
        frappe.model.set_value(leg.doctype, leg.name, 'unit', row.unit);
        if (row.custom_plan_code) {
            frappe.model.set_value(leg.doctype, leg.name, 'custom_plan_code', row.custom_plan_code);
        }
        if (row.plan_name) {
            frappe.model.set_value(leg.doctype, leg.name, 'plan_name', row.plan_name);
        }
        frm.refresh_field('items');
        setTimeout(function () {
            registerWorkingSheetCuttingChangeBomButton(frm);
        }, 100);
    },
    custom_plan_code: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        const leg = _findLegacyRowForPlanned(frm, row);
        if (!leg) return;
        if (row.custom_plan_code) {
            frappe.model.set_value(leg.doctype, leg.name, 'custom_plan_code', row.custom_plan_code);
        }
        if (row.plan_name) {
            frappe.model.set_value(leg.doctype, leg.name, 'plan_name', row.plan_name);
        }
        frm.refresh_field('items');
    },
});

function planningSheetBomLineLabel(row, idx) {
    const code = _norm(row?.item_code);
    const name = _norm(row?.item_name);
    const qty = row?.qty ? ` - ${row.qty} ${row.uom || ''}` : '';
    const serial = Number.isFinite(idx) ? `${idx + 1}. ` : '';
    return `${serial}${code}${name ? ` - ${name}` : ''}${qty}`;
}

function planningSheetBomOptionLabel(bom) {
    const children = (bom?.children || [])
        .map((it) => `${it.item_code}${it.qty ? ` (${it.qty})` : ''}`)
        .join(', ');
    return `${bom.label || bom.name}${children ? ` -> ${children}` : ''}`;
}

function openSheetCuttingChangeBomDialog(frm) {
    frappe.call({
        method: 'production_entry.production_planning.scheduler_api.get_sheet_cutting_bom_change_options',
        args: { planning_sheet_name: frm.doc.name },
        freeze: true,
        freeze_message: __('Loading Sheet Cutting BOMs...'),
        callback: function (r) {
            const rows = (r.message && r.message.rows) || [];
            if (!rows.length) {
                frappe.msgprint({
                    title: __('No Sheet Cutting BOMs'),
                    message: __('No 251 Sheet Cutting Sales Order rows with submitted active BOMs were found.'),
                    indicator: 'orange',
                });
                return;
            }
            const byKey = {};
            rows.forEach((row) => {
                byKey[row.sales_order_item] = row;
            });
            const firstKey = rows[0].sales_order_item;
            const lineOptions = rows.map((row, idx) => planningSheetBomLineLabel(row, idx)).join('\n');
            const d = new frappe.ui.Dialog({
                title: __('Change Sheet Cutting BOM'),
                fields: [
                    {
                        fieldname: 'sales_order_item',
                        fieldtype: 'Select',
                        label: __('Finished Goods Row'),
                        reqd: 1,
                        options: lineOptions,
                        default: planningSheetBomLineLabel(rows[0], 0),
                        onchange: function () {
                            const selectedLabel = d.get_value('sales_order_item') || '';
                            const selected =
                                rows.find((row, idx) => planningSheetBomLineLabel(row, idx) === selectedLabel) || rows[0];
                            const bomOptions = (selected.boms || []).map(planningSheetBomOptionLabel).join('\n');
                            d.fields_dict.bom_no.df.options = bomOptions;
                            d.fields_dict.bom_no.refresh();
                            d.set_value('bom_no', planningSheetBomOptionLabel((selected.boms || [])[0] || {}));
                        },
                    },
                    {
                        fieldname: 'bom_no',
                        fieldtype: 'Select',
                        label: __('BOM'),
                        reqd: 1,
                        options: ((rows[0].boms || []).map(planningSheetBomOptionLabel)).join('\n'),
                        default: planningSheetBomOptionLabel((rows[0].boms || [])[0] || {}),
                    },
                    {
                        fieldname: 'help',
                        fieldtype: 'HTML',
                        options:
                            '<div class="text-muted small">' +
                            __('Only the BOM child rows for the selected 251 line will be replaced. The finished goods row stays unchanged.') +
                            '</div>',
                    },
                ],
                primary_action_label: __('Confirm'),
                primary_action: function () {
                    const selectedLabel = d.get_value('sales_order_item') || '';
                    const selected =
                        rows.find((row, idx) => planningSheetBomLineLabel(row, idx) === selectedLabel) || byKey[firstKey];
                    const selectedBomLabel = d.get_value('bom_no') || '';
                    const bom = (selected.boms || []).find((b) => planningSheetBomOptionLabel(b) === selectedBomLabel);
                    if (!selected || !bom) {
                        frappe.msgprint(__('Please select both Finished Goods row and BOM.'));
                        return;
                    }
                    frappe.call({
                        method: 'production_entry.production_planning.scheduler_api.apply_sheet_cutting_bom_to_planning_sheet',
                        args: {
                            planning_sheet_name: frm.doc.name,
                            sales_order_item: selected.sales_order_item,
                            bom_no: bom.name,
                        },
                        freeze: true,
                        freeze_message: __('Replacing BOM child items...'),
                        callback: function (res) {
                            const m = res.message || {};
                            d.hide();
                            frappe.show_alert({
                                message: __(m.message || 'BOM child rows updated.'),
                                indicator: 'green',
                            });
                            frm.reload_doc();
                        },
                    });
                },
            });
            d.show();
        },
    });
}

function openWorkingBomPickerForFgRow(frm, fgRow) {
    const itemCode = _norm(fgRow?.item_code);
    if (!itemCode) return;
    frappe.call({
        method: 'production_entry.production_planning.scheduler_api.get_sheet_cutting_bom_change_options',
        args: { planning_sheet_name: frm.doc.name },
        freeze: true,
        freeze_message: __('Loading Sheet Cutting BOMs...'),
        callback: function (r) {
            const rows = (r.message && r.message.rows) || [];
            const selected = rows.find((row) => _norm(row.item_code) === itemCode);
            if (!selected) {
                frappe.msgprint(__('No 251 Sheet Cutting row found for {0}', [itemCode]));
                return;
            }
            const boms = selected.boms || [];
            if (!boms.length) {
                frappe.msgprint(__('No active BOM for {0}', [itemCode]));
                return;
            }
            const defaultBom = (boms.find((b) => b.is_default) || boms[0]).name;
            const d = new frappe.ui.Dialog({
                title: __('Select BOM'),
                fields: [
                    {
                        fieldtype: 'HTML',
                        fieldname: 'info',
                        options:
                            '<p><b>' +
                            frappe.utils.escape_html(selected.item_code || '') +
                            '</b><br>' +
                            frappe.utils.escape_html(selected.item_name || '') +
                            '</p>',
                    },
                    {
                        fieldtype: 'Select',
                        fieldname: 'bom_no',
                        label: __('BOM'),
                        options: boms.map((b) => b.name).join('\n'),
                        default: defaultBom,
                        reqd: 1,
                    },
                ],
                primary_action_label: __('Confirm'),
                primary_action: function (values) {
                    frappe.call({
                        method: 'production_entry.production_planning.scheduler_api.apply_sheet_cutting_bom_to_planning_sheet',
                        args: {
                            planning_sheet_name: frm.doc.name,
                            sales_order_item: selected.sales_order_item,
                            bom_no: values.bom_no,
                        },
                        freeze: true,
                        freeze_message: __('Replacing BOM child items...'),
                        callback: function (res) {
                            const m = res.message || {};
                            d.hide();
                            frappe.show_alert({
                                message: __(m.message || 'BOM child rows updated.'),
                                indicator: 'green',
                            });
                            frm.reload_doc();
                        },
                    });
                },
            });
            d.show();
        },
    });
}

function installWorkingSheetCuttingBomPicker(frm) {
    if (!frm || !frm.doc || !frm.doc.name) return;
    window.open_bom_picker = function (fgRow) {
        openWorkingBomPickerForFgRow(frm, fgRow);
    };
}

function registerWorkingSheetCuttingChangeBomButton(frm) {
    if (!frm || !frm.doc || !frm.doc.name) return;
    installWorkingSheetCuttingBomPicker(frm);
    try {
        frm.remove_custom_button(__('Change BOM'), __('Actions'));
    } catch (e) {}
    frm.add_custom_button(__('Change BOM'), function () {
        openSheetCuttingChangeBomDialog(frm);
    }, __('Actions'));
}

frappe.ui.form.on('Planning sheet', {
    refresh: function(frm) {
        if (!frm.doc || !frm.doc.name) return;
        ps_schedule_planning_grid_columns(frm);
        registerWorkingSheetCuttingChangeBomButton(frm);
        // Site Client Scripts may re-add their own non-saving Change BOM button after app scripts.
        setTimeout(function () {
            registerWorkingSheetCuttingChangeBomButton(frm);
        }, 300);
        setTimeout(function () {
            registerWorkingSheetCuttingChangeBomButton(frm);
        }, 1000);
        if (typeof register_planning_sheet_stock_check_button === 'function') {
            register_planning_sheet_stock_check_button(frm);
            setTimeout(function () { register_planning_sheet_stock_check_button(frm); }, 300);
            setTimeout(function () { register_planning_sheet_stock_check_button(frm); }, 1000);
        }
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
        frm.add_custom_button(__('Fill Parent Child Trace IDs'), function () {
            frappe.call({
                method: 'production_entry.production_planning.scheduler_api.ensure_planning_sheet_trace_ids',
                args: { planning_sheet_name: frm.doc.name },
                freeze: true,
                freeze_message: __('Stamping trace IDs on all rows…'),
                callback: function (r) {
                    const m = r.message || {};
                    frappe.show_alert({
                        message: __('Updated {0} row(s)', [m.updated || 0]),
                        indicator: (m.updated || 0) > 0 ? 'green' : 'orange',
                    });
                    frm.reload_doc();
                },
            });
        }, __('Actions'));
    },

    items_add: function (frm) {
        ps_schedule_planning_grid_columns(frm);
        setTimeout(function () {
            registerWorkingSheetCuttingChangeBomButton(frm);
        }, 100);
    },

    items_remove: function (frm) {
        ps_schedule_planning_grid_columns(frm);
        setTimeout(function () {
            registerWorkingSheetCuttingChangeBomButton(frm);
        }, 100);
    },

    planned_items_add: function (frm) {
        ps_schedule_planning_grid_columns(frm);
    },

    planned_items_remove: function (frm) {
        ps_schedule_planning_grid_columns(frm);
    },

    after_load: function(frm) {
        // Align ``Planning sheet Item`` + ``Planning Table`` DB Select metadata (rewinding lineup)
        // with board; clears stale client DocType caches so grids show the full unit list.
        frappe.call({
            method: 'production_entry.production_planning.scheduler_api.sync_planning_line_unit_options_meta',
            callback: function () {
                try {
                    ['Planning sheet Item', 'Planning Table'].forEach(function (dt) {
                        if (locals.DocType && locals.DocType[dt]) delete locals.DocType[dt];
                    });
                } catch (e) {}
                frappe.model.with_doctype('Planning sheet Item', function () {
                    frappe.model.with_doctype('Planning Table', function () {
                        frm.refresh_field('items');
                        frm.refresh_field('planned_items');
                        ps_schedule_planning_grid_columns(frm);
                        try {
                            if (frm.fields_dict.custom_planned_items) frm.refresh_field('custom_planned_items');
                        } catch (e2) {}
                    });
                });
            },
        });

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
