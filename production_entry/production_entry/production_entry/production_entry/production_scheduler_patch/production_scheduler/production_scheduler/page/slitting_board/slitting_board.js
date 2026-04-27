frappe.pages["slitting-board"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Slitting Board",
		single_column: true,
	});

	$(page.body).html('<div id="production-scheduler-app"></div>');

	new production_scheduler.Controller(document.getElementById("production-scheduler-app"));
};
