frappe.pages["w-cut-d-cut-order-table"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: "W CUT / D CUT Table",
		single_column: true,
	});

	wrapper.controller = new production_scheduler.BoxBagOrderTableController(wrapper);
};
