// Planning Sheet Custom Script - Display customer name instead of ID
frappe.ui.form.on('Planning sheet', {
    refresh: function(frm) {
        if (!frm.doc || !frm.doc.name) return;
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
    },

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
