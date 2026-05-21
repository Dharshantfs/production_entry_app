// Transfer Approval form — Approve / Reject (same APIs as transfer-approval page).
const TL_API = "production_entry.production_planning.transfer_logistics";

function can_act_on_transfer_approval() {
	return frappe.user_roles.some((r) =>
		["System Manager", "Manufacturing Manager", "Administrator"].includes(r)
	);
}

frappe.ui.form.on("Transfer Approval", {
	refresh(frm) {
		frm.add_custom_button(__("Open Approval Dashboard"), () => {
			frappe.set_route("transfer-approval");
		});

		if (!frm.is_new() && ["Pending Approval", "Draft"].includes(frm.doc.status)) {
			if (can_act_on_transfer_approval()) {
				frm.add_custom_button(
					__("Approve & Create Stock Entry"),
					() => approve_transfer(frm),
					__("Approve")
				).addClass("btn-primary");

				frm.add_custom_button(__("Reject"), () => reject_transfer(frm), __("Reject"));
			} else {
				frm.dashboard.add_comment(
					__("Only Manufacturing Manager / System Manager can approve transfers."),
					"blue",
					true
				);
			}
		}

		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("View Stock Entry"), () => {
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry);
			});
		}
	},
});

function approve_transfer(frm) {
	frappe.confirm(
		__("Approve this transfer and create draft Stock Entry?"),
		() => {
			frappe.call({
				method: `${TL_API}.approve_transfer_approval`,
				args: { name: frm.doc.name },
				freeze: true,
				freeze_message: __("Approving…"),
				callback(r) {
					const ste = r.message?.stock_entry;
					frappe.show_alert({
						message: ste
							? __("Approved — Stock Entry {0}", [ste])
							: __("Transfer approved"),
						indicator: "green",
					});
					frm.reload_doc();
					if (ste) frappe.set_route("Form", "Stock Entry", ste);
				},
			});
		}
	);
}

function reject_transfer(frm) {
	frappe.confirm(__("Reject this transfer request?"), () => {
		frappe.call({
			method: `${TL_API}.reject_transfer_approval`,
			args: { name: frm.doc.name },
			freeze: true,
			callback() {
				frappe.show_alert({ message: __("Transfer rejected"), indicator: "orange" });
				frm.reload_doc();
			},
		});
	});
}
