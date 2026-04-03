frappe.pages["production-board"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Production Board",
        single_column: true,
    });

    // Create the mount point for Vue
    $(page.body).html('<div id="production-scheduler-app"></div>');

    // Mount the Vue component
    new production_scheduler.Controller(
        document.getElementById("production-scheduler-app")
    );
};
