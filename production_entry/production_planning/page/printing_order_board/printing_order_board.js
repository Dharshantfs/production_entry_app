frappe.pages["printing-order-board"].on_page_load = function (wrapper) {
    frappe.ui.make_app_page({
        parent: wrapper,
        title: "Printing Order Board",
        single_column: true,
    });

    try {
        wrapper.controller = new production_scheduler.PrintingOrderBoardController(wrapper);
    } catch (e) {
        console && console.warn && console.warn('PrintingOrderBoardController not found in production_scheduler bundle');
    }
};
