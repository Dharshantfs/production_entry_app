frappe.pages["color-chart"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Color Chart",
        single_column: true,
    });

    // Create the mount point for Vue
    $(page.body).html('<div id="color-chart-app"></div>');

    // Mount the Vue component
    new production_scheduler.ColorChartController(
        document.getElementById("color-chart-app")
    );
};
