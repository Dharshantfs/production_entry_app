// Shaft Production Run — Roll Production Results (child: Shaft Production Run Item)
// Row background bands by produced GSM (same bands as unit routing: >50, >20, >10, else)

frappe.ui.form.on('Shaft Production Run', {
    production_plan: function (frm) {
        if (!frm.doc.production_plan) {
            frm.clear_table('jobs');
            frm.clear_table('items');
            frm.refresh_field('jobs');
            frm.refresh_field('items');
            return;
        }

        if (!frm.doc.run_date) {
            frm.set_value('run_date', frappe.datetime.get_today());
        }

        frappe.call({
            method:
                'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_production_plan_details',
            args: { production_plan: frm.doc.production_plan },
            callback: function (r) {
                const d = r.message || {};
                if (d.customer) {
                    frm.set_value('customer', d.customer);
                }
                if (d.custom_unit) {
                    frm.set_value('custom_unit', d.custom_unit);
                }
            },
        });

        frappe.call({
            method:
                'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_job_rows_for_production_plan',
            args: { production_plan: frm.doc.production_plan },
            freeze: true,
            freeze_message: __('Loading jobs from Work Orders...'),
            callback: function (r) {
                frm.clear_table('jobs');
                (r.message || []).forEach(function (row) {
                    let c = frm.add_child('jobs');
                    c.job_no = row.job_no;
                    c.job_id = row.job_no || row.job_id;
                    c.total_weight = row.total_weight;
                });
                frm.refresh_field('jobs');

                frappe.call({
                    method:
                        'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_item_rows_for_production_plan',
                    args: { production_plan: frm.doc.production_plan },
                    freeze: true,
                    freeze_message: __('Loading roll lines from Work Orders...'),
                    callback: function (r2) {
                        frm.clear_table('items');
                        (r2.message || []).forEach(function (row) {
                            let it = frm.add_child('items');
                            [
                                'job_no',
                                'job',
                                'wo_id',
                                'work_order',
                                'planned_qty',
                                'wo_status',
                                'so_item',
                                'item_code',
                                'item_name',
                                'shaft_combination',
                                'unit',
                                'dot_spec',
                                'quality',
                                'color',
                                'gsm',
                                'custom_production_gsm',
                                'width_inches',
                                'width_inch',
                                'meter',
                                'meter_per_roll',
                                'meter_roll',
                                'no_of_rolls',
                                'weight_per_roll',
                                'uom',
                                'batch_no',
                                'roll_no',
                                'net_weight',
                                'gross_weight',
                                'custom_produced_length_mtrs',
                                'custom_cbm',
                                'custom_diameter',
                                'custom_core_width_mm',
                                'custom_shift',
                                'custom_party_code_text',
                                'party_code',
                                'order_code',
                                'warehouse',
                                'allocated_to_unit',
                                'row_ready_for_print',
                                'row_locked',
                                'row_printed',
                            ].forEach(function (k) {
                                if (row[k] !== undefined && row[k] !== null) {
                                    it[k] = row[k];
                                }
                            });
                        });
                        frm.refresh_field('items');
                        schedule_apply_gsm_row_colors(frm);
                    },
                });
            },
        });
    },

    refresh: function (frm) {
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Create Roll Production Entry'), function () {
                create_roll_production_entry(frm);
            }).addClass('btn-primary');
        }
        schedule_apply_gsm_row_colors(frm);
    },

    onload: function (frm) {
        schedule_apply_gsm_row_colors(frm);
    },

    items_add: function (frm) {
        schedule_apply_gsm_row_colors(frm);
    },

    items_remove: function (frm) {
        schedule_apply_gsm_row_colors(frm);
    },
});

frappe.ui.form.on('Shaft Production Run Item', {
    meter_per_roll: function (frm, cdt, cdn) {
        calculate_net_weight_spr_row(frm, cdt, cdn);
        schedule_apply_gsm_row_colors(frm);
    },
    gsm: function (frm, cdt, cdn) {
        calculate_net_weight_spr_row(frm, cdt, cdn);
        schedule_apply_gsm_row_colors(frm);
    },
    width_inches: function (frm, cdt, cdn) {
        calculate_net_weight_spr_row(frm, cdt, cdn);
        schedule_apply_gsm_row_colors(frm);
    },
    width_inch: function (frm, cdt, cdn) {
        calculate_net_weight_spr_row(frm, cdt, cdn);
        schedule_apply_gsm_row_colors(frm);
    },
    meter_roll: function (frm, cdt, cdn) {
        calculate_net_weight_spr_row(frm, cdt, cdn);
        schedule_apply_gsm_row_colors(frm);
    },
    custom_production_gsm: function (frm, cdt, cdn) {
        calculate_net_weight_spr_row(frm, cdt, cdn);
        schedule_apply_gsm_row_colors(frm);
    },
    item_name: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.item_name) {
            schedule_apply_gsm_row_colors(frm);
            return;
        }
        frappe.call({
            method:
                'production_entry.production_planning.doctype.planning_sheet.planning_sheet.extract_quality_and_color',
            args: { item_name: row.item_name },
            callback: function (r) {
                if (r.message && r.message.length >= 2) {
                    frappe.model.set_value(cdt, cdn, 'quality', r.message[0] || '');
                    frappe.model.set_value(cdt, cdn, 'color', r.message[1] || '');
                }
                schedule_apply_gsm_row_colors(frm);
            },
        });
    },
});

function calculate_net_weight_spr_row(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    const gsmVal = flt(row.gsm) || flt(row.custom_production_gsm);
    const wIn = flt(row.width_inches) || flt(row.width_inch);
    const mRoll = flt(row.meter_per_roll) || flt(row.meter_roll);
    if (gsmVal && wIn && mRoll) {
        const width_m = wIn * 0.0254;
        const net_weight = (gsmVal * width_m * mRoll) / 1000;
        frappe.model.set_value(
            cdt,
            cdn,
            'net_weight',
            Math.round(net_weight * 1000) / 1000
        );
    }
}

function gsm_band_background(gsm) {
    const g = flt(gsm);
    if (g > 50) {
        return '#e8f5e9';
    }
    if (g > 20) {
        return '#fff8e1';
    }
    if (g > 10) {
        return '#e3f2fd';
    }
    if (g > 0) {
        return '#f5f5f5';
    }
    return '';
}

function schedule_apply_gsm_row_colors(frm) {
    frappe.after_ajax(function () {
        setTimeout(function () {
            apply_gsm_row_colors(frm);
        }, 200);
    });
}

function apply_gsm_row_colors(frm) {
    const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
    if (!grid || !frm.doc.items || !frm.doc.items.length) {
        return;
    }

    function paint($el, bg) {
        if (!$el || !$el.length) {
            return;
        }
        $el.css('background-color', bg || '');
    }

    if (grid.grid_rows && grid.grid_rows.length) {
        frm.doc.items.forEach(function (row, idx) {
            const bg = gsm_band_background(row.gsm);
            const gr = grid.grid_rows[idx];
            if (!gr) {
                return;
            }
            if (gr.row) {
                paint($(gr.row), bg);
            }
            if (gr.wrapper) {
                paint(gr.wrapper, bg);
            }
        });
        return;
    }

    if (!grid.wrapper) {
        return;
    }
    const $rows = grid.wrapper.find('.grid-body .rows .grid-row');
    frm.doc.items.forEach(function (row, idx) {
        const bg = gsm_band_background(row.gsm);
        const $r = $rows.eq(idx);
        paint($r, bg);
        $r.find('.grid-static-col').each(function () {
            paint($(this), bg);
        });
    });
}

function create_roll_production_entry(frm) {
    frappe.call({
        method:
            'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_or_create_roll_entry',
        args: {
            shaft_production_run: frm.doc.name,
        },
        freeze: true,
        freeze_message: __('Fetching all job details...'),
        callback: function (r) {
            if (r.message) {
                if (r.message.existing) {
                    frappe.set_route('Form', 'Roll Production Entry', r.message.existing);
                } else {
                    let data = r.message;
                    frappe.new_doc('Roll Production Entry', {
                        shaft_production_run: frm.doc.name,
                        production_plan: data.production_plan,
                        items: data.items,
                    });
                }
            }
        },
    });
}
