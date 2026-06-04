frappe.pages["despatch-approval-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Despatch Approval",
		single_column: true,
	});

	$(page.body).html('<div id="despatch-approval-app"></div>');

	const mount = () => {
		const el = document.getElementById("despatch-approval-app");
		if (el && production_scheduler.DespatchApprovalController) {
			new production_scheduler.DespatchApprovalController(el);
			return true;
		}
		return false;
	};

	if (!mount()) {
		$(page.body).html(
			'<div class="text-muted p-5">Loading Despatch Approval dashboard...</div>'
		);
		setTimeout(() => {
			if (!mount()) {
				$(page.body).html(
					'<div class="text-danger p-5">Dashboard failed to load. Run <b>bench build --app production_entry</b> and refresh.</div>'
				);
			}
		}, 1200);
	}
};
