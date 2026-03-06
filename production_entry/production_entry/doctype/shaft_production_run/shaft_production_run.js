frappe.ui.form.on('Shaft Production Run', {
    refresh: function (frm) {
        // Remove standard "Add Row" for shaft_jobs as it should be fetched from PP
        frm.get_field('shaft_jobs').grid.cannot_add_rows = true;
    },
    production_plan: function (frm) {
        if (frm.doc.production_plan) {
            frm.trigger('fetch_shaft_details');
        } else {
            frm.clear_table('shaft_jobs');
            frm.refresh_field('shaft_jobs');
        }
    },
    fetch_shaft_details: function (frm) {
        frappe.call({
            method: 'frappe.client.get_value',
            args: {
                doctype: 'Production Plan',
                filters: { name: frm.doc.production_plan },
                fieldname: 'shaft_details'
            },
            callback: function (r) {
                if (r.message && r.message.shaft_details) {
                    frm.clear_table('shaft_jobs');
                    // In your system, shaft_details is likely a child table on Production Plan
                    // We need to fetch the actual rows
                    frappe.call({
                        method: 'frappe.client.get_list',
                        args: {
                            doctype: 'Shaft Detail', // Assuming the child table name
                            filters: { parent: frm.doc.production_plan },
                            fields: ['job', 'gsm', 'combination', 'total_width', 'total_weight']
                        },
                        callback: function (list_res) {
                            if (list_res.message) {
                                list_res.message.forEach(d => {
                                    let row = frm.add_child('shaft_jobs');
                                    row.job_id = d.job;
                                    row.gsm = d.gsm;
                                    row.combination = d.combination;
                                    row.total_width = d.total_width;
                                    row.planned_weight = d.total_weight;
                                });
                                frm.refresh_field('shaft_jobs');
                            }
                        }
                    });
                }
            }
        });
    }
});

frappe.ui.form.on('Shaft Production Run Job', {
    // When a job is clicked/selected in the summary table
    job_id: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.job_id) {
            frm.trigger('populate_items_from_job', row);
        }
    }
});

// Implementation of the mapping logic
frappe.ui.form.on('Shaft Production Run', {
    populate_items_from_job: function (frm, job_row) {
        // 1. Parse combination string (e.g. "46 + 46 + 26")
        let widths = job_row.combination.split('+').map(s => parseFloat(s.trim()));
        let gsm = job_row.gsm;

        // 2. Fetch Work Orders for this PP matching widths and GSM
        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Work Order',
                filters: {
                    production_plan: frm.doc.production_plan,
                    status: ['in', ['Ready to Manufacture', 'In Progress']],
                    custom_gsm: gsm
                },
                fields: ['name', 'production_item', 'custom_width_inch', 'stock_uom', 'custom_quality', 'custom_color']
            },
            callback: function (r) {
                if (r.message) {
                    // Match each width in combination to a WO
                    widths.forEach(width => {
                        let matching_wo = r.message.find(wo => Math.abs(parseFloat(wo.custom_width_inch) - width) < 0.1);
                        if (matching_wo) {
                            let item_row = frm.add_child('items');
                            item_row.job = job_row.job_id;
                            item_row.work_order = matching_wo.name;
                            item_row.item_code = matching_wo.production_item;
                            item_row.uom = matching_wo.stock_uom;
                            item_row.quality = matching_wo.custom_quality;
                            item_row.color = matching_wo.custom_color;
                            item_row.gsm = gsm;
                            item_row.width_inch = matching_wo.custom_width_inch;
                        }
                    });
                    frm.refresh_field('items');
                }
            }
        });
    }
});
