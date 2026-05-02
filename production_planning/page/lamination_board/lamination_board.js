frappe.pages["lamination-board"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Lamination Board",
		single_column: true,
	});

	$(page.body).html('<div id="production-scheduler-app"></div>');

	const mountEl = document.getElementById("production-scheduler-app");

	const mountController = () => {
		frappe.provide("production_scheduler");
		const Controller = production_scheduler && production_scheduler.Controller;
		if (typeof Controller !== "function") {
			if (mountEl) {
				mountEl.innerHTML =
					'<div style="padding:16px;color:#b91c1c;font-weight:600;">Lamination Board failed to load. Please refresh this page.</div>';
			}
			return;
		}
		new Controller(mountEl);
	};

	if (window.production_scheduler && typeof production_scheduler.Controller === "function") {
		mountController();
		return;
	}

	if (frappe.require) {
		frappe.require("/assets/production_entry/js/scheduler.bundle.js", mountController);
		return;
	}

	mountController();
};
