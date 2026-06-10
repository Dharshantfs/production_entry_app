frappe.pages["confirm-orders"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: "Confirm Orders",
		single_column: true,
	});

	const $main = $(wrapper).find(".layout-main-section");
	$main.html('<div id="confirm-orders-app"></div>');

	const mountEl = $main.find("#confirm-orders-app")[0];

	if (!mountEl) {
		$main.html(
			'<div style="padding:16px;color:#b91c1c;font-weight:700;">Confirm Orders: mount point missing. Contact support.</div>'
		);
		return;
	}

	if (!window.production_scheduler || !production_scheduler.ConfirmedOrderController) {
		mountEl.innerHTML =
			'<div style="padding:16px;color:#b91c1c;font-weight:700;">Confirm Orders UI bundle not loaded. Run <code>bench build --app production_entry</code> and hard-refresh.</div>';
		return;
	}

	try {
		wrapper.controller = new production_scheduler.ConfirmedOrderController(mountEl);
	} catch (e) {
		console.error("Confirm Orders mount failed:", e);
		mountEl.innerHTML =
			'<div style="padding:16px;color:#b91c1c;font-weight:700;">Confirm Orders failed to load. Check browser console.</div>';
	}
};
