frappe.ui.form.on('Shaft Production Run', {
    production_plan: function (frm) {
        if (!frm.doc.production_plan) {
            frm.clear_table('jobs');
            frm.refresh_field('jobs');
            return;
        }
        frappe.call({
            method:
                'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_job_rows_for_production_plan',
            args: {
                production_plan: frm.doc.production_plan,
            },
            freeze: true,
            freeze_message: __('Loading jobs from Work Orders...'),
            callback: function (r) {
                frm.clear_table('jobs');
                (r.message || []).forEach(function (row) {
                    let child = frm.add_child('jobs');
                    child.job_no = row.job_no;
                    child.total_weight = row.total_weight;
                });
                frm.refresh_field('jobs');
            },
        });
    },

    refresh: function (frm) {
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Create Roll Production Entry'), function () {
                create_roll_production_entry(frm);
            }).addClass('btn-primary');
        }
    },
});

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
