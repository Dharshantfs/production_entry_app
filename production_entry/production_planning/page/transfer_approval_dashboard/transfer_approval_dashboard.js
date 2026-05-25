frappe.pages["transfer-approval-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Transfer Approval",
		single_column: true,
	});

	$(page.body).html('<div id="transfer-approval-app"></div>');

	const mount = () => {
		const el = document.getElementById("transfer-approval-app");
		if (el && production_scheduler.TransferApprovalController) {
			new production_scheduler.TransferApprovalController(el);
			return true;
		}
		return false;
	};

	if (!mount()) {
		$(page.body).html(
			'<div class="text-muted p-5">Loading Transfer Approval dashboard...</div>'
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

// Old route alias for users/bookmarks; the DocType list keeps using its own route.
frappe.pages["transfer-approval"] = frappe.pages["transfer-approval-dashboard"];
