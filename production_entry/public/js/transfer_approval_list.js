// Transfer Approval list — open the Vue dashboard (like Sequence Approval), not only the table.

frappe.listview_settings["Transfer Approval"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Open Approval Dashboard"), () => {
			frappe.set_route("transfer-approval-dashboard");
		});
	},
};
