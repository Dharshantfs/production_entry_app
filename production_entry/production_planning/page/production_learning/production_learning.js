frappe.pages["production-learning"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Production Learning",
		single_column: true,
	});

	$(page.body).html('<div id="production-learning-app"></div>');

	new production_scheduler.ProductionLearningController(
		document.getElementById("production-learning-app")
	);
};
