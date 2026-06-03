frappe.ui.form.on("Work Order", {
	refresh(frm) {
		if (frm.is_new() || cint(frm.doc.docstatus) !== 0) {
			return;
		}
		frm.add_custom_button(__("Fix RM Kg (Meter÷factor)"), () => {
			frappe.call({
				method: "production_entry.production_planning.scheduler_api.fix_work_order_rm_stock_qty",
				args: { work_order: frm.doc.name },
				freeze: true,
				callback(r) {
					if (!r.exc) {
						const n = (r.message && r.message.updated) || 0;
						frappe.show_alert({
							message: n
								? __("Updated {0} required item row(s).", [n])
								: __("Required qty already correct."),
							indicator: "green",
						});
						frm.reload_doc();
					}
				},
			});
		}, __("Actions"));
	},
});
