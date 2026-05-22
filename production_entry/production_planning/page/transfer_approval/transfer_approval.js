frappe.pages["transfer-approval"].on_page_load = function (wrapper) {
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
			'<div class="text-muted p-5">Loading Transfer Approval dashboard…</div>'
		);
		setTimeout(() => {
			if (!mount()) {
				$(page.body).html(
					'<div class="text-danger p-5">Transfer Approval dashboard failed to load. Run <b>bench build --app production_entry</b> and refresh.</div>'
				);
			}
		}, 1200);
	}
};
