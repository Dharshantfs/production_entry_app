// Link Delivery Note saved from despatch mapper back to Despatch Approval.

frappe.ui.form.on("Delivery Note", {
	after_save(frm) {
		const da = (frappe.route_options || {}).despatch_approval;
		if (!da || frm.doc.__linked_despatch) {
			return;
		}
		frappe.call({
			method: "production_entry.production_planning.despatch_logistics.link_delivery_note_to_despatch",
			args: {
				despatch_approval: da,
				delivery_note: frm.doc.name,
			},
			callback() {
				frm.doc.__linked_despatch = 1;
				if (frappe.route_options) {
					delete frappe.route_options.despatch_approval;
				}
			},
		});
	},
});
