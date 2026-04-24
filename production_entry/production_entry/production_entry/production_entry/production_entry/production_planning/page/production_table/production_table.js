frappe.pages['production-table'].on_page_load = function (wrapper) {
    frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Production Table',
        single_column: true
    });

    // Register the controller
    wrapper.controller = new production_scheduler.ProductionTableController(wrapper);
};
