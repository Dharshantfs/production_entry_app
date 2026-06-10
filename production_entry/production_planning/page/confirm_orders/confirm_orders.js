// #region agent log
function _coDebugLog(hypothesisId, message, data) {
	const payload = {
		sessionId: "28d245",
		hypothesisId,
		location: "confirm_orders.js",
		message,
		data: data || {},
		timestamp: Date.now(),
		runId: "pre-fix",
	};
	try {
		console.log("[DEBUG-28d245]", payload);
		fetch("http://127.0.0.1:7243/ingest/af933f46-5611-414a-ac86-9735a878ab5a", {
			method: "POST",
			headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "28d245" },
			body: JSON.stringify(payload),
		}).catch(function () {});
	} catch (e) {
		/* ignore */
	}
}
// #endregion

frappe.pages["confirm-orders"].on_page_load = function (wrapper) {
	// #region agent log
	_coDebugLog("H1", "confirm-orders on_page_load start", {
		wrapper: !!wrapper,
		hasProductionScheduler: !!window.production_scheduler,
		hasController: !!(
			window.production_scheduler && production_scheduler.ConfirmedOrderController
		),
	});
	// #endregion

	frappe.ui.make_app_page({
		parent: wrapper,
		title: "Confirm Orders",
		single_column: true,
	});

	const $main = $(wrapper).find(".layout-main-section");
	$main.html('<div id="confirm-orders-app"></div>');

	const mountEl = $main.find("#confirm-orders-app")[0];

	// #region agent log
	_coDebugLog("H3", "mount element resolved", {
		mountEl: !!mountEl,
		mainSection: $main.length,
	});
	// #endregion

	if (!mountEl) {
		$main.html(
			'<div style="padding:16px;color:#b91c1c;font-weight:700;">Confirm Orders: mount point missing. Contact support.</div>'
		);
		return;
	}

	if (!window.production_scheduler || !production_scheduler.ConfirmedOrderController) {
		// #region agent log
		_coDebugLog("H2", "ConfirmedOrderController unavailable", {
			production_scheduler: typeof window.production_scheduler,
		});
		// #endregion
		mountEl.innerHTML =
			'<div style="padding:16px;color:#b91c1c;font-weight:700;">Confirm Orders UI bundle not loaded. Run <code>bench build --app production_entry</code> and hard-refresh.</div>';
		return;
	}

	try {
		wrapper.controller = new production_scheduler.ConfirmedOrderController(mountEl);
		// #region agent log
		_coDebugLog("H4", "ConfirmedOrderController mounted", { ok: true });
		// #endregion
	} catch (e) {
		// #region agent log
		_coDebugLog("H4", "ConfirmedOrderController mount threw", { error: String(e) });
		// #endregion
		console.error("Confirm Orders mount failed:", e);
		mountEl.innerHTML =
			'<div style="padding:16px;color:#b91c1c;font-weight:700;">Confirm Orders failed to load. Check browser console.</div>';
	}
};
