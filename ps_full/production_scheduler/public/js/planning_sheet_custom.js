// Planning Sheet Custom Script - Display customer name instead of ID
frappe.ui.form.on('Planning sheet', {
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
