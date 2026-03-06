frappe.ui.form.on('Shaft Production Run', {
    fetch_work_orders: function (frm) {
        if (!frm.doc.allocated_unit) {
            frappe.msgprint(__('Please select an Allocated Unit (Machine) first'));
            return;
        }

        new frappe.ui.form.MultiSelectDialog({
            doctype: "Work Order",
            target: frm,
            setters: {
                custom_allocated_unit: frm.doc.allocated_unit,
                status: "In Progress"
            },
            add_filters_group: 1,
            get_query() {
                let filters = {
                    status: ["in", ["Ready to Manufacture", "In Progress"]],
                    docstatus: 1,
                    custom_allocated_unit: frm.doc.allocated_unit
                };
                if (frm.doc.production_plan) {
                    filters.production_plan = frm.doc.production_plan;
                }
                return {
                    filters: filters
                }
            },
            action(selections) {
                if (selections.length === 0) return;

                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Work Order',
                        filters: { name: ['in', selections] },
                        fields: ['name', 'production_item', 'qty', 'uom', 'custom_quality', 'custom_color', 'custom_width_inch', 'custom_gsm']
                    },
                    callback: function (r) {
                        if (r.message) {
                            r.message.forEach(function (wo) {
                                let row = frm.add_child('items');
                                row.work_order = wo.name;
                                row.item_code = wo.production_item;
                                row.uom = wo.uom;
                                row.quality = wo.custom_quality;
                                row.color = wo.custom_color;
                                row.width_inch = wo.custom_width_inch;
                                row.gsm = wo.custom_gsm;
                                row.net_weight = 0; // Operator inputs actual roll weight here
                            });
                            frm.refresh_field('items');
                        }
                    }
                });
                this.dialog.hide();
            }
        });
    }
});
