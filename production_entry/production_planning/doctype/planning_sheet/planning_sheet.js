frappe.ui.form.on('Planning sheet', {
    refresh: function(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__('Meter to Kgs (Box Bag BOM)'), function() {
                frappe.call({
                    method: "production_entry.production_planning.scheduler_api.convert_meter_to_kgs_for_box_bag_bom",
                    args: {
                        planning_sheet_name: frm.doc.name
                    },
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.msgprint(__('Converted ' + (r.message.updated || 0) + ' items from Meter to Kgs successfully.'));
                            frm.reload_doc();
                        }
                    }
                });
            }, __('Actions'));
        }
    }
});
