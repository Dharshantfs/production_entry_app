frappe.pages["sequence-approval"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Sequence Approval",
        single_column: true,
    });

    // Create the mount point for Vue
    $(page.body).html('<div id="sequence-approval-app"></div>');

    // Mount the Vue component
    if (production_scheduler.SequenceApprovalController) {
        new production_scheduler.SequenceApprovalController(
            document.getElementById("sequence-approval-app")
        );
    } else {
        $(page.body).html('<div class="text-muted p-5">Loading dashboard components...</div>');
        // Retry if bundle not fully loaded
        setTimeout(() => {
            if (production_scheduler.SequenceApprovalController) {
                $(page.body).html('<div id="sequence-approval-app"></div>');
                new production_scheduler.SequenceApprovalController(
                    document.getElementById("sequence-approval-app")
                );
            }
        }, 1000);
    }
};
