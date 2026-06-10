frappe.pages["confirmed-order"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Confirm Orders",
        single_column: true,
    });

    $(page.body).html('<div id="confirmed-order-app"></div>');

    const mountEl = document.getElementById("confirmed-order-app");
    if (mountEl) {
        mountEl.innerHTML =
            '<div style="padding:16px;color:#111827;font-weight:600;">Loading Confirm Orders…</div>';
    }

    try {
        if (!production_scheduler || !production_scheduler.ConfirmedOrderController) {
            throw new Error("production_scheduler.ConfirmedOrderController is not available");
        }
        new production_scheduler.ConfirmedOrderController(mountEl);
    } catch (e) {
        console.error("Confirm Orders mount failed:", e);
        if (mountEl) {
            mountEl.innerHTML =
                '<div style="padding:16px;color:#b91c1c;font-weight:700;">Confirm Orders failed to load. Check console.</div>';
        }
    }
};
