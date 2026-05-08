frappe.pages["printing-order-table"].on_page_load = function (wrapper) {
    frappe.ui.make_app_page({
        parent: wrapper,
        title: "Printing Order Table",
        single_column: true,
    });

    // Controller class `PrintingOrderTableController` should be provided in scheduler bundle.
    // This mirrors other page registration patterns (e.g., slitting-order-table).
    try {
        wrapper.controller = new production_scheduler.PrintingOrderTableController(wrapper);
    } catch (e) {
        // If controller not present yet, log and leave page skeleton.
        console && console.warn && console.warn('PrintingOrderTableController not found in production_scheduler bundle');
    }
};
