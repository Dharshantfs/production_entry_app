frappe.pages["confirmed-order"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Confirmed Order",
        single_column: true,
    });

    // Create the mount point for Vue (Proven pattern from color_chart.js)
    $(page.body).html('<div id="confirmed-order-app"></div>');

    // Always render a placeholder first so the page is never blank.
    const mountEl = document.getElementById("confirmed-order-app");
    if (mountEl) {
        mountEl.innerHTML =
            '<div style="padding:16px;color:#111827;font-weight:600;">Loading confirmed orders...</div>';
    }

    // Quick server check (so if Vue mounting fails, we still know API works).
    try {
        frappe.call({
            method: "production_scheduler.api.get_confirmed_orders_kanban",
            args: { order_date: frappe.datetime.get_today() },
            callback: function (r) {
                try {
                    const count = Array.isArray(r && r.message) ? r.message.length : 0;
                    if (mountEl) {
                        mountEl.innerHTML =
                            '<div style="padding:16px;color:#111827;font-weight:600;">Confirmed Orders loaded: ' +
                            count +
                            "</div>";
                    }
                } catch (e) {
                    // Ignore UI update errors
                }
            },
            error: function (err) {
                if (mountEl) {
                    mountEl.innerHTML =
                        '<div style="padding:16px;color:#b91c1c;font-weight:700;">Confirmed Orders API failed to load.</div>';
                }
                console.error("Confirmed Orders API error:", err);
            },
        });
    } catch (e) {
        console.error("Confirmed Orders preflight call failed:", e);
    }

    // Mount the Vue component (if it compiles)
    try {
        console.log("ConfirmedOrder on_page_load mount start");
        if (!production_scheduler || !production_scheduler.ConfirmedOrderController) {
            throw new Error("production_scheduler.ConfirmedOrderController is not available");
        }
        new production_scheduler.ConfirmedOrderController(mountEl);
    } catch (e) {
        console.error("ConfirmedOrder mount failed:", e);
        if (mountEl) {
            mountEl.innerHTML =
                '<div style="padding:16px;color:#b91c1c;font-weight:700;">Confirmed Order failed to load. Check console.</div>';
        }
    }
};


