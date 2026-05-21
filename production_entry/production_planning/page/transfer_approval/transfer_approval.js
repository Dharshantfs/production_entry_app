frappe.pages["transfer-approval"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Transfer Approval",
		single_column: true,
	});
	const mount = () => {
		const el = document.getElementById("transfer-approval-app");
		if (el && production_scheduler.TransferApprovalController) {
			new production_scheduler.TransferApprovalController(el);
			return true;
		}
		return false;
	};
	$(page.body).html('<div id="transfer-approval-app"></div>');
	if (!mount()) {
		const t = setInterval(() => {
			if (mount()) clearInterval(t);
		}, 200);
		setTimeout(() => clearInterval(t), 8000);
	}
};
