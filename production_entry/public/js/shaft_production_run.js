frappe.ui.form.on('Shaft Production Run', {
    refresh: function(frm) {
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Create Roll Production Entry'), function() {
                create_roll_production_entry(frm);
            }).addClass('btn-primary');
        }
    }
});

function create_roll_production_entry(frm) {
    frappe.call({
        method: 'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_or_create_roll_entry',
        args: {
            shaft_production_run: frm.doc.name
        },
        freeze: true,
        freeze_message: __('Fetching all job details...'),
        callback: function(r) {
            if (r.message) {
                if (r.message.existing) {
                    // Open existing Roll Production Entry
                    frappe.set_route('Form', 'Roll Production Entry', r.message.existing);
                } else {
                    // Create new with all jobs pre-filled
                    let data = r.message;
                    frappe.new_doc('Roll Production Entry', {
                        shaft_production_run: frm.doc.name,
                        production_plan: data.production_plan,
                        items: data.items
                    });
                }
            }
        }
    });
}

