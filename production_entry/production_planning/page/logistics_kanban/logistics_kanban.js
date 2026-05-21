frappe.pages["logistics-kanban"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: "Logistics Kanban",
		single_column: true,
	});
	$(wrapper).find(".layout-main-section").html('<div id="logistics-kanban-app"></div>');
	if (production_scheduler.LogisticsKanbanController) {
		new production_scheduler.LogisticsKanbanController(
			document.getElementById("logistics-kanban-app")
		);
	}
};
