frappe.ui.form.on('Shaft Production Run', {
    refresh: function (frm) {
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
            method: 'production_entry.production_entry.doctype.shaft_production_run.shaft_production_run.get_shaft_jobs',
            args: {
                production_plan: frm.doc.production_plan
            },
            callback: function (r) {
                if (r.message) {
                    frm.clear_table('shaft_jobs');
                    r.message.forEach(d => {
                        let row = frm.add_child('shaft_jobs');
                        Object.assign(row, d);
                    });
                    frm.refresh_field('shaft_jobs');
                }
            }
        });
    },
    populate_items_from_job: function (frm, job_row) {
        let combination = job_row.combination || "";
        // Extract widths from combination (e.g. "46 + 46 + 26")
        let widths = combination.split('+').map(s => {
            let val = parseFloat(s.trim().replace(/[^0-9.]/g, ''));
            return val;
        }).filter(w => !isNaN(w));

        let gsm = job_row.gsm;

        if (widths.length === 0) {
            frappe.msgprint("No valid widths found in combination: " + combination);
            return;
        }

        // Clear existing items for this job OR clear all? 
        // User says "need entry for each job id", usually means one job at a time.
        // Let's clear ALL produced rolls to avoid mess, as selection of a job is a "Set" action.
        frm.clear_table('items');

        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Work Order',
                filters: {
                    production_plan: frm.doc.production_plan,
                    docstatus: 1,
                    status: ['in', ['Ready to Manufacture', 'In Progress']],
                    custom_gsm: gsm
                },
                fields: ['name', 'production_item', 'custom_width_inch', 'stock_uom', 'custom_quality', 'custom_color', 'custom_gsm']
            },
            callback: function (r) {
                if (r.message && r.message.length > 0) {
                    widths.forEach(width => {
                        // Find a WO where width matches (allowing small tolerance)
                        let matching_wo = r.message.find(wo => {
                            let wo_width = parseFloat(wo.custom_width_inch || 0);
                            return Math.abs(wo_width - width) < 0.25; // slightly wider tolerance
                        });

                        if (matching_wo) {
                            let item_row = frm.add_child('items');
                            item_row.job = job_row.job_id;
                            item_row.work_order = matching_wo.name;
                            item_row.item_code = matching_wo.production_item;
                            item_row.uom = matching_wo.stock_uom;
                            item_row.quality = matching_wo.custom_quality;
                            item_row.color = matching_wo.custom_color;
                            item_row.gsm = matching_wo.custom_gsm || gsm;
                            item_row.width_inch = matching_wo.custom_width_inch;

                            // Also set roll details to 0/empty to ensure user enters them as mistakes were made previously
                            item_row.net_weight = 0;
                            item_row.gross_weight = 0;
                        } else {
                            frappe.show_alert({
                                message: `Work Order not found for Width ${width}" and GSM ${gsm}`,
                                indicator: 'orange'
                            });
                        }
                    });
                    frm.refresh_field('items');
                } else {
                    frappe.msgprint(`No matching Work Orders found in this Production Plan with GSM ${gsm}.`);
                }
            }
        });
    }
});

frappe.ui.form.on('Shaft Production Run Job', {
    job_id: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.job_id) {
            frm.trigger('populate_items_from_job', row);
        }
    }
});
