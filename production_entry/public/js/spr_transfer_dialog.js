// SPR form — open transfer dialog (uses production_scheduler.openSprTransferDialog from scheduler.bundle.js)
frappe.provide("production_entry.spr_transfer");

production_entry.spr_transfer.open = function (frm) {
	if (!frm || !frm.doc || !frm.doc.name) {
		return;
	}
	if (cint(frm.doc.docstatus) !== 1) {
		frappe.msgprint(__("Submit the SPR before transfer."));
		return;
	}
	if (typeof production_scheduler.openSprTransferDialog === "function") {
		production_scheduler.openSprTransferDialog(frm.doc.name);
		return;
	}
	frappe.msgprint(
		__("Transfer dialog not loaded. Run bench build --app production_entry and refresh the page.")
	);
};
