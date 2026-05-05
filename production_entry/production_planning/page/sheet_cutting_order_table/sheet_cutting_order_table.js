frappe.pages["sheet-cutting-order-table"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: "Sheet Cutting Order Table",
		single_column: true,
	});

	wrapper.controller = new production_scheduler.SheetCuttingOrderTableController(wrapper);
};
