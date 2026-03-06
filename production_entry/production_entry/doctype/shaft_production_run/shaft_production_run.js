frappe.ui.form.on('Shaft Production Run', {
    refresh: function (frm) {
        frm.get_field('shaft_jobs').grid.cannot_add_rows = true;

        if (frm.doc.docstatus === 0) {
            frm.set_intro(__('Please select a Production Plan. Submit this document to start creating Roll Production Entries.'), 'blue');
        }

        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Create Roll Production Entry'), function () {
                frappe.call({
                    method: 'production_entry.production_entry.doctype.shaft_production_run.shaft_production_run.get_or_create_roll_entry',
                    args: {
                        shaft_production_run: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __('Fetching job details...'),
                    callback: function (r) {
                        if (r.message) {
                            if (r.message.existing) {
                                frappe.set_route('Form', 'Roll Production Entry', r.message.existing);
                            } else {
                                frappe.new_doc('Roll Production Entry', {
                                    shaft_production_run: frm.doc.name,
                                    production_plan: r.message.production_plan,
                                    roll_wise_entry: r.message.roll_wise_entry
                                });
                            }
                        }
                    }
                });
            }).addClass('btn-primary');
        }
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

                    if (r.message.length > 0) {
                        frappe.show_alert({
                            message: __('{0} jobs fetched. Submit to proceed.').format(r.message.length),
                            indicator: 'green'
                        });
                    }
                }
            }
        });
    }
});
