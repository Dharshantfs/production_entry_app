// Transfer STE: show destination company on Party when set from Transfer Approval.
frappe.ui.form.on("Stock Entry", {
	refresh(frm) {
		const co = (frm.doc.custom_transfer_to_company || "").trim();
		if (!co) return;
		if (frm.fields_dict.party_type && !frm.doc.party_type) {
			frm.set_value("party_type", "Company");
		}
		if (frm.fields_dict.party && !frm.doc.party) {
			frm.set_value("party", co);
		}
	},
});
