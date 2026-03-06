frappe.ui.form.on('Production Entry', {
    refresh: function (frm) {
        if (frm.doc.docstatus === 1 && frm.doc.status === "In Production") {
            frm.add_custom_button(__('Single Production Entry'), function () {
                frappe.confirm(__('Generate Production Entry for all items in this run?'), function () {
                    frm.call('make_consolidated_entry').then(r => {
                        if (r.message) {
                            frappe.msgprint(r.message.join('<br>'));
                            frm.reload_doc();
                        }
                    });
                });
            }, __('Actions'));
        }
    },

    sales_order: function (frm) {
        if (frm.doc.sales_order) {
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Sales Order',
                    name: frm.doc.sales_order
                },
                callback: function (r) {
                    if (r.message) {
                        frm.clear_table('items');
                        r.message.items.forEach(function (item) {
                            let row = frm.add_child('items');
                            row.so_item = item.name;
                            row.item_code = item.item_code;
                            row.item_name = item.item_name;
                            row.qty = item.qty;
                            row.uom = item.uom;
                            // Pre-fill specs if available in item name
                        });
                        frm.refresh_field('items');
                    }
                }
            });
        }
    }
});
