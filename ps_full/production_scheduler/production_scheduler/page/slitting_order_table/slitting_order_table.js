frappe.pages["slitting-order-table"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: "Slitting Order Table",
		single_column: true,
	});

	wrapper.controller = new production_scheduler.SlittingOrderTableController(wrapper);
};
