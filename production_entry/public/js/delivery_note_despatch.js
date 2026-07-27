// Delivery Note — link back to Despatch Approval + Accounts billing/address helper.

frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;
		frm.add_custom_button(
			__("Accounts: Billing & Address"),
			() => jsb_dn_accounts_address_dialog(frm),
			__("Accounts")
		);
	},

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

function jsb_dn_accounts_address_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Accounts: Billing & Shipping Address"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted">${__(
					"DN team scans and loads only. Accounts sets bill-to / addresses here. Club ID stays on the produced Planning Table rows even if Despatch Customer differs."
				)}</p>`,
			},
			{
				label: __("Bill-to / DN Customer"),
				fieldname: "customer",
				fieldtype: "Link",
				options: "Customer",
				reqd: 1,
				default: frm.doc.customer,
			},
			{
				label: __("Billing Address"),
				fieldname: "customer_address",
				fieldtype: "Link",
				options: "Address",
				default: frm.doc.customer_address,
				get_query() {
					return {
						query: "frappe.contacts.doctype.address.address.address_query",
						filters: {
							link_doctype: "Customer",
							link_name: d.get_value("customer") || frm.doc.customer,
						},
					};
				},
			},
			{
				label: __("Shipping Address"),
				fieldname: "shipping_address_name",
				fieldtype: "Link",
				options: "Address",
				default: frm.doc.shipping_address_name,
				get_query() {
					return {
						query: "frappe.contacts.doctype.address.address.address_query",
						filters: {
							link_doctype: "Customer",
							link_name: d.get_value("customer") || frm.doc.customer,
						},
					};
				},
			},
		],
		primary_action_label: __("Apply"),
		primary_action(values) {
			frm.set_value("customer", values.customer);
			if (values.customer_address) {
				frm.set_value("customer_address", values.customer_address);
			}
			if (values.shipping_address_name) {
				frm.set_value("shipping_address_name", values.shipping_address_name);
			}
			d.hide();
			frappe.show_alert({
				message: __("Customer / addresses updated — Save the DN."),
				indicator: "green",
			});
		},
	});
	d.show();
}
