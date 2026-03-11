frappe.ui.form.on('Shaft Production Run', {
    setup: function (frm) {
        frm.set_df_property('filter_job_id', 'fieldtype', 'Select');
        frm.set_df_property('filter_job_id', 'options', ['All']);
    },
    refresh: function (frm) {
        if (frm.doc.production_plan) {
            frm.add_custom_button(__('Select Work Orders'), function () {
                select_work_orders(frm);
            }, __('Actions'));
        }

        update_job_filter_options(frm);
        setup_grid_filter(frm);

        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Add Manual Job'), function () {
                add_manual_job_dialog(frm);
            }, __('Actions'));
            // Disable manual row addition to the grid itself to force use of buttons/fetch
            frm.get_field('shaft_jobs').grid.cannot_add_rows = true;
        }

        if (frm.is_new()) {
            set_shift_production(frm);
        }

        toggle_mix_roll_fields(frm);
    },

    is_mix_roll: function (frm) {
        toggle_mix_roll_fields(frm);
    },

    custom_unit: function (frm) {
        if (frm.doc.is_mix_roll) {
            frm.call("generate_batch_numbers");
        }
    },

    production_plan: function (frm) {
        if (frm.doc.production_plan) {
            fetch_shaft_details(frm);
        }
    },

    filter_job_id: function (frm) {
        apply_grid_filter(frm);
    },

    before_save: function (frm) {
        // Double check cleanup before every save. 
        // We MUST preserve rows that have a job ID (newly added rolls) or item_code.
        if (frm.doc.items) {
            frm.doc.items = frm.doc.items.filter(r => r.job || r.work_order || r.item_code || (r.net_weight && r.net_weight > 0));
        }
    },

    validate: function (frm) {
        // Aggressively remove empty default rows to prevent mandatory validation errors
        if (frm.doc.items) {
            let initial_len = frm.doc.items.length;
            // Mix Rolls often lack Work Orders, and new rolls have 0 weight. 
            // We MUST preserve rows that have a JOB ID or an ITEM CODE.
            frm.doc.items = frm.doc.items.filter(r => r.job || r.work_order || r.item_code || (r.net_weight && r.net_weight > 0));
            if (frm.doc.items.length !== initial_len) {
                frm.refresh_field('items');
            }
        }
    },

    shift: function (frm) {
        if (frm.doc.items && frm.doc.items.length > 0) {
            frm.call({
                doc: frm.doc,
                method: 'generate_batch_numbers',
                callback: function (r) {
                    if (r.message) {
                        frm.refresh_field('items');
                        frappe.show_alert({
                            message: __('Batch numbers updated for shift: {0}', [frm.doc.shift]),
                            indicator: 'blue'
                        });
                    }
                }
            });
        }
    }
});

function fetch_shaft_details(frm) {
    frappe.call({
        method: 'production_entry.production_entry.doctype.shaft_production_run.shaft_production_run.get_shaft_jobs',
        args: {
            production_plan: frm.doc.production_plan
        },
        callback: function (r) {
            if (r.message) {
                var jobs = r.message.jobs || [];
                var label_type = r.message.label_type || "Default";

                frm.clear_table('shaft_jobs');
                frm.set_value('custom_label', label_type);
                frm.set_value('custom_unit', r.message.custom_unit || "");
                frm.set_value('custom_order_code', r.message.all_party_codes || "");

                if (jobs.length > 0) {
                    frm.is_fetching_details = true;
                    jobs.forEach(function (d) {
                        var job_row = frm.add_child('shaft_jobs');
                        frappe.model.set_value(job_row.doctype, job_row.name, 'job_id', String(d.job_id));
                        frappe.model.set_value(job_row.doctype, job_row.name, 'gsm', d.gsm);
                        frappe.model.set_value(job_row.doctype, job_row.name, 'combination', d.combination);
                        frappe.model.set_value(job_row.doctype, job_row.name, 'total_width', d.total_width);
                        frappe.model.set_value(job_row.doctype, job_row.name, 'meter_roll_mtrs', d.meter_roll_mtrs);
                        frappe.model.set_value(job_row.doctype, job_row.name, 'net_weight', d.net_weight);
                        frappe.model.set_value(job_row.doctype, job_row.name, 'total_weight', d.total_weight);
                        frappe.model.set_value(job_row.doctype, job_row.name, 'no_of_shafts', d.no_of_shafts);
                        frappe.model.set_value(job_row.doctype, job_row.name, 'work_orders', d.work_orders);
                        frappe.model.set_value(job_row.doctype, job_row.name, 'party_code', d.party_code);
                    });

                    frm.refresh_field('shaft_jobs');
                    update_job_filter_options(frm);
                    frm.is_fetching_details = false;

                    // Auto-generate batch numbers if shift is already present
                    if (frm.doc.shift && frm.doc.custom_unit) {
                        frm.call({
                            doc: frm.doc,
                            method: 'generate_batch_numbers',
                            callback: function (r) {
                                if (r.message) {
                                    frm.refresh_field('items');
                                }
                            }
                        });
                    }

                    // Show Work Order Status Dialog
                    if (r.message.wo_summary && r.message.wo_summary.length > 0) {
                        let wo_html = `
                            <table class="table table-bordered table-condensed" style="margin-top: 10px;">
                                <thead>
                                    <tr>
                                        <th>Work Order</th>
                                        <th>Item</th>
                                        <th>Qty</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${r.message.wo_summary.map(wo => `
                                        <tr>
                                            <td>${wo.name}</td>
                                            <td>${wo.item}</td>
                                            <td>${wo.qty}</td>
                                            <td><span class="label label-${wo.status === 'Completed' ? 'success' : (wo.status === 'In Progress' ? 'orange' : 'default')}">${wo.status}</span></td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        `;

                        frappe.msgprint({
                            title: __('Work Order Statuses for Plan'),
                            message: wo_html,
                            wide: true
                        });
                    }

                    frappe.show_alert({
                        message: `Fetched ${jobs.length} jobs from Production Plan.`,
                        indicator: 'green'
                    });
                }
            }
        }
    });
}

frappe.ui.form.on('Shaft Production Run Job', {
    net_weight: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (row.net_weight) {
            var val_str = row.net_weight.toString().trim();
            // Don't format while typing the formula
            if (val_str.endsWith('+') || val_str.endsWith('.')) return;

            var sum = 0;
            var base_part = val_str.includes('=') ? val_str.split('=')[0] : val_str;
            var parts = base_part.split('+');
            parts.forEach(p => {
                var p_val = parseFloat(p.trim());
                if (!isNaN(p_val)) sum += p_val;
            });

            if (sum > 0) {
                frappe.model.set_value(cdt, cdn, 'total_weight', sum);
                // Auto-append calculation result for clarity
                var formatted = base_part.trim() + " = " + sum.toFixed(2);
                if (!val_str.includes('=') && val_str !== formatted) {
                    frappe.model.set_value(cdt, cdn, 'net_weight', formatted);
                }
            }
        }
    },
    job_id: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (row.job_id && frm.doc.production_plan && !row.is_manual) {
            frappe.call({
                method: 'production_entry.production_entry.doctype.shaft_production_run.shaft_production_run.get_shaft_jobs',
                args: { production_plan: frm.doc.production_plan },
                callback: function (r) {
                    if (r.message && r.message.jobs) {
                        var job_match = r.message.jobs.find(j => String(j.job_id) === String(row.job_id));
                        if (job_match) {
                            frappe.model.set_value(cdt, cdn, 'gsm', job_match.gsm);
                            frappe.model.set_value(cdt, cdn, 'combination', job_match.combination);
                            frappe.model.set_value(cdt, cdn, 'total_width', job_match.total_width);
                            frappe.model.set_value(cdt, cdn, 'meter_roll_mtrs', job_match.meter_roll_mtrs);
                            frappe.model.set_value(cdt, cdn, 'net_weight', job_match.net_weight);
                            frappe.model.set_value(cdt, cdn, 'total_weight', job_match.total_weight);
                            frappe.model.set_value(cdt, cdn, 'no_of_shafts', job_match.no_of_shafts);
                            frappe.model.set_value(cdt, cdn, 'party_code', job_match.party_code);

                            // Automatic Selection Dialog for Work Orders removed as per user request
                        }
                    }
                }
            });
        }
    },
    create_roll_entry: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];

        // Cleanup empty rows before fetching to keep the grid clean
        if (frm.doc.items) {
            var to_keep = frm.doc.items.filter(r => r.work_order || r.item_code || (r.net_weight && r.net_weight > 0));
            var to_remove = frm.doc.items.filter(r => !r.work_order && !r.item_code && !(r.net_weight && r.net_weight > 0));
            to_remove.forEach(r => frappe.model.clear_doc('Shaft Production Run Item', r.name));
            frm.doc.items = to_keep;
            frm.refresh_field('items');
        }

        // Call logic - it will handle saving AFTER adding rolls to satisfy mandatory validation
        execute_create_roll_entry(frm, row);
    }
});

function execute_create_roll_entry(frm, row) {
    var wos = [];
    if (row.work_orders && row.work_orders.trim() !== "") {
        wos = row.work_orders.split(',').map(s => s.trim()).filter(s => s);
    }

    var claimed_wos = [];
    if (frm.doc.shaft_jobs) {
        frm.doc.shaft_jobs.forEach(j => {
            if (j.job_id !== row.job_id && j.work_orders) {
                j.work_orders.split(',').forEach(wo => {
                    if (wo.trim()) claimed_wos.push(wo.trim());
                });
            }
        });
    }

    frappe.call({
        method: 'production_entry.production_entry.doctype.shaft_production_run.shaft_production_run.get_job_roll_details',
        args: {
            production_plan: frm.doc.production_plan,
            job_id: row.job_id,
            combination: row.combination,
            no_of_shafts: parseInt(row.no_of_shafts) || 1,
            gsm: parseFloat(row.gsm) || 0,
            meter_roll: parseFloat(row.meter_roll_mtrs) || 0,
            net_weight: row.net_weight,
            work_orders: wos.length > 0 ? JSON.stringify(wos) : null,
            claimed_wos: claimed_wos.length > 0 ? JSON.stringify(claimed_wos) : null,
            parent_spr: frm.is_new() ? null : frm.doc.name,
            manual_item_list: row.manual_items || null,
            is_mix_roll: frm.doc.is_mix_roll || 0,
            party_code: row.party_code || null
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                var rolls_to_add = r.message;
                var max_roll = 0;

                // Cleanup empty rows before adding new ones
                if (frm.doc.items) {
                    var to_keep = frm.doc.items.filter(r => r.work_order || r.item_code || (r.net_weight && r.net_weight > 0));
                    var to_remove = frm.doc.items.filter(r => !r.work_order && !r.item_code && !(r.net_weight && r.net_weight > 0));
                    to_remove.forEach(r => frappe.model.clear_doc('Shaft Production Run Item', r.name));
                    frm.doc.items = to_keep;

                    // Find max roll no among existing items
                    frm.doc.items.forEach(r_row => {
                        var rn = parseInt(r_row.roll_no) || 0;
                        if (rn > max_roll) max_roll = rn;
                    });
                }
                frm.refresh_field('items');

                rolls_to_add.forEach(function (d) {
                    var child = frm.add_child('items');
                    frappe.model.set_value(child.doctype, child.name, 'job', String(d.job || ""));
                    frappe.model.set_value(child.doctype, child.name, 'work_order', d.work_order || "");
                    frappe.model.set_value(child.doctype, child.name, 'item_code', d.item_code || "");
                    frappe.model.set_value(child.doctype, child.name, 'planned_qty', d.planned_qty);
                    frappe.model.set_value(child.doctype, child.name, 'width_inch', d.width_inch);
                    frappe.model.set_value(child.doctype, child.name, 'gsm', d.gsm);
                    frappe.model.set_value(child.doctype, child.name, 'meter_roll', d.meter_roll);
                    frappe.model.set_value(child.doctype, child.name, 'net_weight', d.net_weight);
                    frappe.model.set_value(child.doctype, child.name, 'quality', d.quality);
                    frappe.model.set_value(child.doctype, child.name, 'color', d.color);
                    frappe.model.set_value(child.doctype, child.name, 'uom', 'Kg'); // Force to Kg explicitly
                    frappe.model.set_value(child.doctype, child.name, 'party_code', d.party_code);

                    max_roll++;
                    frappe.model.set_value(child.doctype, child.name, 'roll_no', max_roll);
                });

                frm.refresh_field('items');
                update_job_filter_options(frm);
                apply_grid_filter(frm);
                frm.set_value('filter_job_id', row.job_id);

                if (typeof calculate_total === "function") {
                    calculate_total(frm);
                }

                // Save now - items exist, so mandatory validation will pass
                frm.save().then(function () {
                    frm.call({
                        doc: frm.doc,
                        method: 'generate_batch_numbers',
                        callback: function (resp) {
                            if (resp.message && !resp.exc) {
                                frappe.model.sync(resp.message);
                                frm.refresh();
                                frappe.msgprint({
                                    title: 'Success',
                                    message: 'Successfully added ' + rolls_to_add.length + ' rolls for Job ' + row.job_id + '.',
                                    indicator: 'green'
                                });
                            }
                        }
                    });
                });
            } else {
                frappe.msgprint("Could not find matching Work Orders for this Job's widths. Ensure WOs are created and not closed/cancelled.");
            }
        }
    });
}

frappe.ui.form.on('Shaft Production Run Item', {
    item_code: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (row.job && parseInt(row.job) > 0) {
            frappe.model.set_value(cdt, cdn, 'uom', 'Kg');
        }
    },
    uom: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (row.job && parseInt(row.job) > 0 && row.uom !== 'Kg') {
            frappe.model.set_value(cdt, cdn, 'uom', 'Kg');
            frappe.show_alert({ message: "UOM forced to Kg for manual products.", indicator: "orange" });
        }
    },
    net_weight: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (row.net_weight && !row.gross_weight) {
            frappe.model.set_value(cdt, cdn, 'gross_weight', row.net_weight);
        }
        calculate_total(frm);
    },
    meter_roll: function (frm, cdt, cdn) {
        // Just for re-triggering save if needed
    },
    items_remove: function (frm) {
        calculate_total(frm);
    },
    print_sticker: function (frm, cdt, cdn) {
        frappe.generate_sticker_flow(cdn, frm);
    }
});

function calculate_total(frm) {
    var total = 0.0;
    var job_sums = {};
    var job_formulas = {};

    (frm.doc.items || []).forEach(function (row) {
        var nw = flt(row.net_weight);
        total += nw;
        if (row.job) {
            var jid = String(row.job).trim();
            job_sums[jid] = (job_sums[jid] || 0) + nw;
            if (!job_formulas[jid]) job_formulas[jid] = [];
            job_formulas[jid].push(nw.toFixed(2));
        }
    });
    frm.set_value('total_produced_weight', total);

    // Update Job rows
    (frm.doc.shaft_jobs || []).forEach(function (job) {
        var jid = String(job.job_id).trim();
        if (job_sums[jid] !== undefined) {
            job.total_weight = job_sums[jid];
            job.net_weight = job_formulas[jid].join(" + ") + " = " + job_sums[jid].toFixed(3);
        } else if (job.is_manual) {
            // Reset weights for manual jobs if no rolls found
            job.total_weight = 0;
            job.net_weight = "0";
        }
    });
    frm.refresh_field('shaft_jobs');
}

function update_job_filter_options(frm) {
    var options = ["All"];
    (frm.doc.shaft_jobs || []).forEach(function (j) {
        if (j.job_id && !options.includes(String(j.job_id))) {
            options.push(String(j.job_id));
        }
    });

    frm.set_df_property('filter_job_id', 'fieldtype', 'Select');
    frm.set_df_property('filter_job_id', 'options', options.join('\n'));

    if (!frm.doc.filter_job_id) {
        frm.set_value('filter_job_id', 'All');
    }
}

frappe.ui.form.on('Shaft Production Run Item', {
    item_code: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (row.item_code && !row.uom) {
            frappe.model.set_value(cdt, cdn, 'uom', 'Kg');
        }
    }
});

function toggle_mix_roll_fields(frm) {
    let mode = frm.doc.is_mix_roll;

    // Hide Production Plan and its Section
    frm.toggle_display('production_plan', !mode);

    // Show custom_unit for both, but read-only for standard runs
    frm.toggle_display('custom_unit', true);
    frm.set_df_property('custom_unit', 'read_only', !mode);

    // Ensure options are strictly enforced (overriding any buggy Property Setters cached in UI)
    if (mode && frm.fields_dict.custom_unit) {
        frm.set_df_property('custom_unit', 'options', ["UNIT 1", "UNIT 2", "UNIT 3", "UNIT 4"].join('\n'));
    }

    // Hide Work Order columns in grids
    frm.fields_dict.shaft_jobs.grid.get_docfield('work_orders').hidden = mode;
    frm.fields_dict.items.grid.get_docfield('work_order').hidden = mode;

    // Item Code should NOT be read-only for Mix Rolls
    frm.fields_dict.items.grid.get_docfield('item_code').read_only = !mode;

    frm.fields_dict.shaft_jobs.grid.refresh();
    frm.fields_dict.items.grid.refresh();
}

function add_manual_job_dialog(frm) {
    if (!frm.doc.production_plan) {
        frappe.msgprint(__("Please select a Production Plan first."));
        return;
    }

    let selected_items = []; // [{item_code, item_name, width_inch, gsm}]

    let d = new frappe.ui.Dialog({
        title: __('Add Manual Job'),
        size: 'large',
        fields: [
            {
                fieldname: 'item_select',
                fieldtype: 'Link',
                label: 'Search & Add Product',
                options: 'Item',
                only_select: 1,
                get_query: function () {
                    return {
                        filters: { is_stock_item: 1, disabled: 0 }
                    };
                }
            },
            {
                fieldname: 'btn_add',
                fieldtype: 'Button',
                label: 'Add Product',
                click: function () {
                    let item_code = d.get_value('item_select');
                    if (!item_code) {
                        frappe.show_alert({ message: __('Select an item first'), indicator: 'orange' });
                        return;
                    }
                    
                    // Use get_value to check existence without triggering modal error
                    frappe.db.get_value('Item', item_code, ['name', 'item_name', 'item_code', 'custom_gsm'], (r) => {
                        if (r && r.name) {
                            let item = r;
                            let details = extract_details_enhanced(item.item_name || item.item_code, item.item_code);
                            selected_items.push({
                                item_code: item.item_code,
                                item_name: item.item_name || item.item_code,
                                width_inch: parseFloat(details.width_inch) || 0,
                                gsm: parseInt(details.gsm) || parseInt(item.custom_gsm) || 0
                            });
                            d.set_value('item_select', '');
                            refresh_manual_job_preview(d, selected_items);
                        } else {
                            frappe.msgprint({
                                title: __('Item Not Found'),
                                message: __('Item code <b>{0}</b> does not exist in the Item master. Please ensure the item is created first.', [item_code]),
                                indicator: 'red'
                            });
                        }
                    });
                }
            },
            {
                fieldname: 'products_html',
                fieldtype: 'HTML',
                label: 'Selected Products'
            },
            { fieldtype: 'Section Break', label: 'Job Summary' },
            {
                fieldname: 'combination_display',
                fieldtype: 'Data',
                label: 'Combination',
                read_only: 1
            },
            {
                fieldname: 'total_width_display',
                fieldtype: 'Float',
                label: 'Total Width (Inches)',
                read_only: 1
            },
            { fieldtype: 'Column Break' },
            {
                fieldname: 'gsm_display',
                fieldtype: 'Data',
                label: 'GSM',
                read_only: 1
            },
            {
                fieldname: 'gsm_alert_html',
                fieldtype: 'HTML'
            },
            { fieldtype: 'Section Break' },
            {
                fieldname: 'no_of_shafts',
                fieldtype: 'Int',
                label: 'Number of Shafts',
                default: 4,
                reqd: 1,
                onchange: function () { refresh_manual_job_preview(d, selected_items); }
            },
            { fieldtype: 'Column Break' },
            {
                fieldname: 'meter_roll',
                fieldtype: 'Float',
                label: 'Meter / Roll',
                default: 800,
                reqd: 1,
                onchange: function () { refresh_manual_job_preview(d, selected_items); }
            },
            { fieldtype: 'Section Break', label: 'Production Preview' },
            {
                fieldname: 'production_preview_html',
                fieldtype: 'HTML'
            }
        ],
        primary_action_label: __('Create Job'),
        primary_action: function (values) {
            if (selected_items.length === 0) {
                frappe.msgprint(__('Please add at least one product.'));
                return;
            }

            // GSM mismatch check
            let gsm_values = selected_items.map(i => flt(i.gsm)).filter(g => g > 0);
            let unique_gsms = [...new Set(gsm_values)];
            if (unique_gsms.length > 1) {
                let max_diff = Math.max(...unique_gsms) - Math.min(...unique_gsms);
                if (max_diff > 1) {
                    frappe.msgprint({
                        title: __('GSM Mismatch'),
                        message: __('Selected items have different GSM values: {0}. All items in one job should have the same GSM.', [unique_gsms.join(', ')]),
                        indicator: 'red'
                    });
                    return;
                }
            }

            // Width check
            let widths_missing = selected_items.filter(i => !i.width_inch || flt(i.width_inch) <= 0);
            if (widths_missing.length > 0) {
                frappe.msgprint({
                    title: __('Missing Width'),
                    message: __('Could not determine width for: {0}. Ensure item names contain width in inches (e.g. 46 inch, 46").', [widths_missing.map(i => i.item_name).join(', ')]),
                    indicator: 'orange'
                });
                return;
            }

            execute_manual_job_from_dialog(frm, selected_items, values, d);
        }
    });
    d.show();
    refresh_manual_job_preview(d, selected_items);
}

function refresh_manual_job_preview(dialog, selected_items) {
    let html = '';
    if (selected_items.length === 0) {
        html = '<div style="padding: 20px; text-align: center; color: #888;">No products added yet. Search and add products above.</div>';
    } else {
        html = '<table class="table table-bordered table-condensed" style="margin-top: 5px; margin-bottom: 0;">' +
            '<thead><tr style="background: #f5f5f5;">' +
            '<th style="width:30px">#</th>' +
            '<th>Item Code</th>' +
            '<th>Item Name</th>' +
            '<th style="width:80px">Width</th>' +
            '<th style="width:60px">GSM</th>' +
            '<th style="width:40px"></th>' +
            '</tr></thead><tbody>';
        selected_items.forEach(function (item, idx) {
            html += '<tr>' +
                '<td>' + (idx + 1) + '</td>' +
                '<td><strong>' + item.item_code + '</strong></td>' +
                '<td>' + item.item_name + '</td>' +
                '<td>' + (item.width_inch ? item.width_inch + '"' : '<span style="color:red">?</span>') + '</td>' +
                '<td>' + (item.gsm || '<span style="color:red">?</span>') + '</td>' +
                '<td style="text-align:center"><button class="btn btn-xs btn-danger remove-manual-item" data-idx="' + idx + '">&times;</button></td>' +
                '</tr>';
        });
        html += '</tbody></table>';
    }

    dialog.fields_dict.products_html.$wrapper.html(html);

    // Calculate Production Preview
    let shafts = parseInt(dialog.get_value('no_of_shafts')) || 0;
    let meters = parseFloat(dialog.get_value('meter_roll')) || 0;
    let preview_html = '';

    if (selected_items.length > 0 && shafts > 0 && meters > 0) {
        // Group by item code to match eventual Work Order creation
        let groups = {};
        selected_items.forEach(item => {
            if (!groups[item.item_code]) {
                groups[item.item_code] = {
                    item_code: item.item_code,
                    width_inch: flt(item.width_inch),
                    gsm: flt(item.gsm),
                    count: 0
                };
            }
            groups[item.item_code].count += 1;
        });

        preview_html = '<div style="margin-bottom:10px;"><small class="text-muted">Expected Work Orders based on this configuration:</small></div>' +
            '<table class="table table-bordered table-condensed" style="background: #fffbe6;">' +
            '<thead><tr style="font-size: 11px; color: #555;">' +
            '<th>Item Code</th>' +
            '<th>Net Weight/Roll</th>' +
            '<th>Total WO Qty (Kg)</th>' +
            '</tr></thead><tbody>';

        Object.values(groups).forEach(g => {
            // Formula: (gsm * width * meters * 0.0254) / 1000
            let nw = (g.gsm * g.width_inch * meters * 0.0254) / 1000;
            let total_qty = nw * shafts * g.count;
            preview_html += '<tr>' +
                '<td>' + g.item_code + ' (x' + g.count + ')</td>' +
                '<td>' + nw.toFixed(3) + ' Kg</td>' +
                '<td><strong>' + total_qty.toFixed(3) + ' Kg</strong></td>' +
                '</tr>';
        });
        preview_html += '</tbody></table>';
    } else if (selected_items.length > 0) {
        preview_html = '<div class="text-muted" style="font-size: 12px; padding: 10px;">Enter Shafts and Meter/Roll to see production preview.</div>';
    }

    if (dialog.fields_dict.production_preview_html) {
        dialog.fields_dict.production_preview_html.$wrapper.html(preview_html);
    }

    // Bind remove buttons
    dialog.fields_dict.products_html.$wrapper.find('.remove-manual-item').on('click', function () {
        let idx = parseInt($(this).attr('data-idx'));
        selected_items.splice(idx, 1);
        refresh_manual_job_preview(dialog, selected_items);
    });

    // Update combination, total width, GSM
    let widths = selected_items.map(function (i) { return flt(i.width_inch); }).filter(function (w) { return w > 0; });
    let combination = widths.map(function (w) { return w + '"'; }).join(' + ');
    let total_width = widths.reduce(function (sum, w) { return sum + w; }, 0);

    let gsm_values = selected_items.map(function (i) { return flt(i.gsm); }).filter(function (g) { return g > 0; });
    let unique_gsms = [];
    gsm_values.forEach(function (g) { if (unique_gsms.indexOf(g) === -1) unique_gsms.push(g); });
    let gsm_display = unique_gsms.length > 0 ? String(unique_gsms[0]) : '';
    let gsm_mismatch = unique_gsms.length > 1 && (Math.max.apply(null, unique_gsms) - Math.min.apply(null, unique_gsms) > 1);

    dialog.set_value('combination_display', combination || '');
    dialog.set_value('total_width_display', total_width);
    dialog.set_value('gsm_display', gsm_display);

    // GSM alert
    let alert_html = '';
    if (gsm_mismatch) {
        alert_html = '<div class="alert alert-danger" style="margin:5px 0;padding:6px 10px;font-size:12px;"><strong>GSM Mismatch!</strong> Values: ' + unique_gsms.join(', ') + '</div>';
    }
    dialog.fields_dict.gsm_alert_html.$wrapper.html(alert_html);
}

function execute_manual_job_from_dialog(frm, selected_items, values, dialog) {
    let max_id = 0;
    (frm.doc.shaft_jobs || []).forEach(j => {
        let id = parseInt(j.job_id) || 0;
        if (id > max_id) max_id = id;
    });
    let new_job_id = String(max_id + 1);

    // Group items by item_code to sum the manufactured qty if user selects identical items (e.g. 42 + 42 + 42)
    let grouped_items = {};
    selected_items.forEach(function (item) {
        if (!grouped_items[item.item_code]) {
            grouped_items[item.item_code] = {
                item_code: item.item_code,
                item_name: item.item_name,
                width_inch: flt(item.width_inch),
                gsm: flt(item.gsm),
                count: 0
            };
        }
        grouped_items[item.item_code].count += 1;
    });

    let widths = selected_items.map(function (i) { return flt(i.width_inch); });
    let combination_str = widths.map(function (w) { return w + '"'; }).join(' + ');
    let total_width = widths.reduce(function (s, w) { return s + w; }, 0);
    let common_gsm = selected_items[0].gsm || 0;

    frappe.show_alert({ message: __('Creating Work Orders for {0} distinct items...', [Object.keys(grouped_items).length]), indicator: 'blue' });

    let new_wos = [];
    let wo_errors = [];
    let promises = Object.keys(grouped_items).map(function (item_code) {
        let item = grouped_items[item_code];
        return new Promise(function (resolve) {
            // Formula requested by user: ((gsm * width * meter/roll * 0.0254)/1000)
            let net_weight_per_roll = (flt(item.gsm) * flt(item.width_inch) * values.meter_roll * 0.0254) / 1000;
            // Total manufactured qty for this item's Work Order (net weight * no of shafts * count of this item in job)
            let qty = net_weight_per_roll * values.no_of_shafts * item.count;

            frappe.call({
                method: 'production_entry.production_entry.doctype.shaft_production_run.shaft_production_run.create_manual_work_order',
                args: {
                    production_plan: frm.doc.production_plan,
                    item_code: item.item_code,
                    qty: qty
                },
                callback: function (res) {
                    if (res.message) new_wos.push(res.message);
                    resolve();
                },
                error: function () {
                    wo_errors.push(item.item_code);
                    resolve();
                }
            });
        });
    });

    Promise.all(promises).then(function () {
        if (new_wos.length === 0) {
            frappe.msgprint({
                title: __('Error'),
                message: __('Failed to create Work Orders. Please check that items have active BOMs.'),
                indicator: 'red'
            });
            return;
        }

        let job_row = frm.add_child('shaft_jobs');
        job_row.job_id = new_job_id;
        job_row.gsm = common_gsm;
        job_row.combination = combination_str;
        job_row.total_width = total_width;
        job_row.meter_roll_mtrs = values.meter_roll;
        job_row.no_of_shafts = values.no_of_shafts;
        job_row.is_manual = 1;

        let manual_items_arr = selected_items.map(function (i) { return i.item_code; });
        job_row.manual_items = JSON.stringify(manual_items_arr);
        job_row.work_orders = new_wos.join(', ');

        // Calculate exact string: 74.78 + 74.78 + 42.27 = 191.83
        let net_weights = selected_items.map(function (item) {
            let w = flt(item.width_inch);
            let g = flt(item.gsm) || common_gsm;
            let nw = (g * w * values.meter_roll * 0.0254) / 1000;
            return nw;
        });

        let net_weights_str = net_weights.map(function (nw) { return nw.toFixed(2); }).join(' + ');
        let total_net_weight = net_weights.reduce(function (s, a) { return s + a; }, 0);

        job_row.net_weight = net_weights_str + " = " + total_net_weight.toFixed(2);
        // User requested: total weight is sum of combination netweight * no of shafts
        job_row.total_weight = total_net_weight * values.no_of_shafts;

        frm.refresh_field('shaft_jobs');
        update_job_filter_options(frm);
        dialog.hide();

        let msg = __('Manual Job {0} created', [new_job_id]) +
            '<br>Combination: <strong>' + combination_str + '</strong>' +
            '<br>Work Orders: ' + new_wos.join(', ');
        if (wo_errors.length > 0) {
            msg += '<br><br><span style="color:orange">Warning: Could not create WO for: ' + wo_errors.join(', ') + '</span>';
        }
        frappe.msgprint({ title: __('Manual Job Created'), message: msg, indicator: 'green' });
    });
}

function setup_grid_filter(frm) {
    if (frm.get_field('items')) {
        var grid = frm.get_field('items').grid;
        var old_refresh = grid.refresh;
        grid.refresh = function () {
            old_refresh.apply(grid, arguments);
            // Delay slightly to ensure DOM is rendered
            setTimeout(function() {
                apply_grid_filter(frm);
            }, 50);
        };
        frm.fields_dict['items'].grid.on_grid_refresh = function () {
            setTimeout(function() {
                apply_grid_filter(frm);
            }, 50);
        };
    }
}

function apply_grid_filter(frm) {
    var raw_filter = frm.doc.filter_job_id || "All";
    var filter = String(raw_filter).trim();
    var grid = frm.get_field('items').grid;
    if (!grid || !grid.wrapper) return;

    var job_colors = {};
    var color_palette = ['#2980b9', '#27ae60', '#8e44ad', '#f39c12', '#c0392b', '#16a085', '#2c3e50'];
    var color_idx = 0;

    $(grid.wrapper).find('.grid-row').each(function () {
        var name = $(this).attr('data-name');
        var row = (frm.doc.items || []).find(r => r.name === name);
        if (!row) return;

        var row_job = String(row.job || "").trim();

        if (row_job) {
            if (!job_colors[row_job]) {
                job_colors[row_job] = color_palette[color_idx % color_palette.length];
                color_idx++;
            }
            $(this).css('border-left', '5px solid ' + job_colors[row_job]);
        }

        if (filter !== "All" && row_job !== filter) {
            $(this).hide();
        } else {
            $(this).show();
        }
    });

    if (filter !== "All") {
        $(grid.wrapper).find('.grid-footer').hide();
    } else {
        $(grid.wrapper).find('.grid-footer').show();
    }
}

function select_work_orders(frm) {
    var d = new frappe.ui.form.MultiSelectDialog({
        doctype: "Work Order",
        target: frm,
        setters: {
            production_plan: frm.doc.production_plan
        },
        add_filters_group: 1,
        columns: ["status", "production_plan", "item_code", "qty"],
        get_query() {
            return {
                filters: {
                    production_plan: frm.doc.production_plan,
                    docstatus: 1,
                    status: ["not in", ["Cancelled", "Closed"]]
                }
            };
        },
        primary_action(selections) {
            if (selections && selections.length > 0) {
                fetch_jobs_for_wos(frm, selections);
                d.dialog.hide();
            } else {
                frappe.msgprint("Please select at least one Work Order.");
            }
        }
    });
}

function fetch_jobs_for_wos(frm, work_orders) {
    frappe.call({
        method: 'production_entry.production_entry.doctype.shaft_production_run.shaft_production_run.get_shaft_jobs',
        args: {
            production_plan: frm.doc.production_plan,
            work_orders: work_orders
        },
        callback: function (r) {
            if (r.message) {
                var jobs = r.message.jobs || [];
                var label_type = r.message.label_type || "Default";

                frm.clear_table('shaft_jobs');
                if (jobs.length > 0) {
                    jobs.forEach(function (d) {
                        var job_row = frm.add_child('shaft_jobs');
                        job_row.job_id = d.job_id;
                        job_row.gsm = d.gsm;
                        job_row.combination = d.combination;
                        job_row.total_width = d.total_width;
                        job_row.meter_roll_mtrs = d.meter_roll_mtrs;
                        job_row.net_weight = d.net_weight;
                        job_row.total_weight = d.total_weight;
                        job_row.no_of_shafts = d.no_of_shafts;
                    });
                    frm.set_value('custom_label', label_type);
                    frm.refresh_field('shaft_jobs');
                }
            }
        }
    });
}

function set_shift_production(frm) {
    var current_hour = new Date().getHours();
    if (current_hour >= 8 && current_hour < 20) {
        frm.set_value('shift', 'Day Shift');
    } else {
        frm.set_value('shift', 'Night Shift');
    }
}

var QUALITY_MASTER = {
    "100": "PREMIUM", "101": "PLATINUM", "102": "SUPER PLATINUM",
    "103": "GOLD", "104": "SILVER", "105": "BRONZE",
    "106": "CLASSIC", "107": "SUPER CLASSIC", "108": "LIFE STYLE",
    "109": "ECO SPECIAL", "110": "ECO GREEN", "111": "SUPER ECO",
    "112": "ULTRA", "113": "DELUXE", "114": "UV",
    "120": "PREMIUM PLUS",
    "012": "ULTRA", "010": "PREMIUM", "011": "PLATINUM"
};

function extract_details_enhanced(name, code) {
    var res = { gsm: null, color: null, width_inch: null, quality: null };
    var name_upper = (name || "").toUpperCase();
    var code_str = String(code || "").trim();

    if (code_str && code_str.length === 16 && /^\d+$/.test(code_str)) {
        // 16-digit decoding rules
        // Quality (3-6)
        var qual_code = code_str.substring(3, 6);
        if (QUALITY_MASTER[qual_code]) res.quality = QUALITY_MASTER[qual_code];

        // Color (6-9) - Use indices if possible
        var color_code = code_str.substring(6, 9);
        // JS doesn't have easy access to DocType data without async calls here, 
        // so we'll rely on item name parsing for color if indices don't map to a name we know.
        // However, we can at least try to extract it from name if code is present.

        // GSM (9-12)
        var code_gsm = parseInt(code_str.substring(9, 12));
        if (code_gsm > 0) res.gsm = String(code_gsm);

        // Width (12-16)
        var code_width_mm = parseFloat(code_str.substring(12, 16));
        if (code_width_mm > 0) res.width_inch = String(Math.round(code_width_mm / 25.4));
    }

    // Pattern matching from name (Fallback or primary for non-16-digit)
    if (name_upper) {
        // Quality lookup from name
        if (!res.quality) {
            var known_qualities = Object.values(QUALITY_MASTER);
            known_qualities.sort(function (a, b) { return b.length - a.length; });
            for (var i = 0; i < known_qualities.length; i++) {
                var q = known_qualities[i];
                if (new RegExp('\\b' + q + '\\b', 'i').test(name_upper)) {
                    res.quality = q;
                    break;
                }
            }
        }

        // GSM lookup from name
        if (!res.gsm) {
            var mg = name_upper.match(/(\d+)\s*GSM/i);
            if (mg) res.gsm = mg[1];
        }

        // Width lookup from name
        if (!res.width_inch) {
            var mw = name_upper.match(/(\d+(\.\d+)?)\s*("|inch|in|''|mm|MM)/i);
            if (mw) res.width_inch = mw[1];
        }

        // Color extraction from name strings
        if (!res.color) {
            // Logic: Take everything after Quality/GSM as color
            var parts = name_upper.split(/(\d+\s*GSM|PLATINUM|PREMIUM|ULTRA|GOLD|SILVER|BRONZE|UV|CLASSIC|DELUXE|STYLE|ECO)/i);
            if (parts.length > 2) {
                var last_part = parts[parts.length - 1].trim();
                // Clean up prefixes like ":" or "-"
                last_part = last_part.replace(/^[\s,:-]+|[\s,:-]+$/g, "");
                if (last_part && last_part.length > 2 && !/^\d+$/.test(last_part)) {
                    res.color = last_part;
                }
            }
        }
    }
    return res;
}
