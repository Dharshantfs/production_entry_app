frappe.listview_settings["Shift Breakdown"] = {
	add_fields: ["machine_status", "last_reason", "open_since", "custom_unit", "shift"],
	get_indicator(doc) {
		if (doc.machine_status === "Off") {
			return [__("Machine Off"), "red", "machine_status,=,Off"];
		}
		return [__("Machine On"), "green", "machine_status,=,On"];
	},
	onload(listview) {
		listview.page.add_inner_button(__("Still Off"), () => {
			listview.filter_area.add([[listview.doctype, "machine_status", "=", "Off"]]);
			listview.refresh();
		});
	},
};
