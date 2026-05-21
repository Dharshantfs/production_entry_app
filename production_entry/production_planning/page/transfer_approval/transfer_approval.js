frappe.pages["transfer-approval"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: "Transfer Approval",
		single_column: true,
	});
	$(wrapper).find(".layout-main-section").html('<div id="transfer-approval-app"></div>');
	if (production_scheduler.TransferApprovalController) {
		new production_scheduler.TransferApprovalController(
			document.getElementById("transfer-approval-app")
		);
	}
};
