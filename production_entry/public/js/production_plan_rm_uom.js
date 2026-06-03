frappe.ui.form.on("Production Plan", {
	refresh(frm) {
		if (!frm.doc.name || frm.doc.docstatus !== 0) {
			return;
		}
		frm.add_custom_button(__("Recalc RM (Meter÷factor)"), () => {
			frappe.call({
				method: "production_entry.production_planning.scheduler_api.fix_production_plan_rm_stock_qty",
				args: { production_plan: frm.doc.name },
				freeze: true,
				callback(r) {
					if (!r.exc) {
						frappe.show_alert({ message: __("Raw materials recalculated"), indicator: "green" });
						frm.reload_doc();
					}
				},
			});
		});
	},
});
