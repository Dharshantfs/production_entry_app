// Delivery Note — link back to Despatch Approval + Accounts billing/address helper.

frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		jsb_bind_dn_item_rolls_buttons(frm);
		if (frm.doc.docstatus !== 0) return;
		frm.add_custom_button(
			__("Accounts: Billing & Address"),
			() => jsb_dn_accounts_address_dialog(frm),
			__("Accounts")
		);
		frm.add_custom_button(
			__("Delete Draft DN"),
			() => jsb_delete_draft_delivery_note(frm),
			__("Delivery")
		);
	},

	items_add(frm) {
		jsb_bind_dn_item_rolls_buttons(frm);
	},

	after_save(frm) {
		const da = (frappe.route_options || {}).despatch_approval;
		if (!da || frm.doc.__linked_despatch) {
			return;
		}
		frappe.call({
			method: "production_entry.production_planning.despatch_logistics.link_delivery_note_to_despatch",
			args: {
				despatch_approval: da,
				delivery_note: frm.doc.name,
			},
			callback() {
				frm.doc.__linked_despatch = 1;
				if (frappe.route_options) {
					delete frappe.route_options.despatch_approval;
				}
			},
		});
	},
});

function jsb_dn_has_despatch_rolls(frm) {
	if (frm.doc.custom_despatch_approval) {
		return true;
	}
	return (frm.doc.items || []).some((row) => row.custom_despatch_rolls_json);
}

function jsb_bind_dn_item_rolls_buttons(frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid || !jsb_dn_has_despatch_rolls(frm)) {
		return;
	}
	setTimeout(() => {
		(grid.grid_rows || []).forEach((gridRow) => {
			const $row = gridRow.row || gridRow.wrapper;
			if (!$row || !$row.find) {
				return;
			}
			if ($row.find(".jsb-dn-rolls-btn").length) {
				return;
			}
			const doc = gridRow.doc;
			if (!doc || !doc.item_code) {
				return;
			}
			if (!doc.custom_despatch_rolls_json && !frm.doc.custom_despatch_approval) {
				return;
			}
			const $btn = $(
				'<button type="button" class="btn btn-xs btn-default jsb-dn-rolls-btn" style="margin-left:6px;">' +
					__("Rolls") +
					"</button>"
			);
			$btn.on("click", (e) => {
				e.preventDefault();
				e.stopPropagation();
				jsb_open_dn_item_rolls_dialog(frm, doc);
			});
			const $target = $row.find(
				'[data-fieldname="item_code"] .static-area, [data-fieldname="item_code"]'
			).last();
			if ($target.length) {
				$target.append($btn);
			} else {
				$row.find(".grid-static-col").last().append($btn);
			}
		});
	}, 200);
}

function jsb_open_dn_item_rolls_dialog(frm, itemRow) {
	if (!frm.doc.name) {
		frappe.msgprint(__("Save the Delivery Note first."));
		return;
	}
	frappe.call({
		method:
			"production_entry.production_planning.despatch_logistics.get_delivery_note_item_rolls",
		args: {
			delivery_note: frm.doc.name,
			item_code: itemRow.item_code,
			child_name: itemRow.name,
		},
		freeze: true,
		callback(r) {
			const msg = r.message || {};
			if (!msg.rolls || !msg.rolls.length) {
				frappe.msgprint(__("No roll details found for this item."));
				return;
			}
			jsb_show_despatch_rolls_dialog({
				rolls: msg.rolls,
				item_code: msg.item_code || itemRow.item_code,
				delivery_note: frm.doc.name,
			});
		},
	});
}

function jsb_delete_draft_delivery_note(frm) {
	const da =
		(frappe.route_options && frappe.route_options.despatch_approval) ||
		frm.doc.__jsb_despatch_approval ||
		"";

	const runDelete = (despatchApproval) => {
		frappe.confirm(
			__(
				"Unlink and delete this draft Delivery Note from Despatch Approval {0}? Other DNs for this club stay untouched.",
				[despatchApproval]
			),
			() => {
				frappe.call({
					method:
						"production_entry.production_planning.despatch_logistics.delete_draft_delivery_note",
					args: {
						delivery_note: frm.doc.name,
						despatch_approval: despatchApproval,
					},
					freeze: true,
					freeze_message: __("Deleting Delivery Note…"),
					callback() {
						frappe.show_alert({
							message: __("Delivery Note deleted"),
							indicator: "green",
						});
						frappe.set_route("List", "Delivery Note");
					},
				});
			}
		);
	};

	if (da) {
		runDelete(da);
		return;
	}

	frappe.call({
		method:
			"production_entry.production_planning.despatch_logistics.get_despatch_approvals_for_delivery_note",
		args: { delivery_note: frm.doc.name },
		callback(r) {
			const linked = (r.message && r.message.approvals) || [];
			if (linked.length === 1) {
				runDelete(linked[0]);
			} else if (linked.length > 1) {
				frappe.msgprint(
					__(
						"This Delivery Note is linked to multiple Despatch Approvals. Delete it from Logistics Kanban (× on the club card) for the correct approval."
					)
				);
			} else {
				frappe.msgprint(
					__(
						"This Delivery Note is not linked to a Despatch Approval. Use the standard Delete action for normal draft DNs."
					)
				);
			}
		},
	});
}

function jsb_dn_accounts_address_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Accounts: Billing & Shipping Address"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted">${__(
					"DN team scans and loads only. Accounts sets bill-to / addresses here. Club ID stays on the produced Planning Table rows even if Despatch Customer differs."
				)}</p>`,
			},
			{
				label: __("Bill-to / DN Customer"),
				fieldname: "customer",
				fieldtype: "Link",
				options: "Customer",
				reqd: 1,
				default: frm.doc.customer,
			},
			{
				label: __("Billing Address"),
				fieldname: "customer_address",
				fieldtype: "Link",
				options: "Address",
				default: frm.doc.customer_address,
				get_query() {
					return {
						query: "frappe.contacts.doctype.address.address.address_query",
						filters: {
							link_doctype: "Customer",
							link_name: d.get_value("customer") || frm.doc.customer,
						},
					};
				},
			},
			{
				label: __("Shipping Address"),
				fieldname: "shipping_address_name",
				fieldtype: "Link",
				options: "Address",
				default: frm.doc.shipping_address_name,
				get_query() {
					return {
						query: "frappe.contacts.doctype.address.address.address_query",
						filters: {
							link_doctype: "Customer",
							link_name: d.get_value("customer") || frm.doc.customer,
						},
					};
				},
			},
		],
		primary_action_label: __("Apply"),
		primary_action(values) {
			frm.set_value("customer", values.customer);
			if (values.customer_address) {
				frm.set_value("customer_address", values.customer_address);
			}
			if (values.shipping_address_name) {
				frm.set_value("shipping_address_name", values.shipping_address_name);
			}
			d.hide();
			frappe.show_alert({
				message: __("Customer / addresses updated — Save the DN."),
				indicator: "green",
			});
		},
	});
	d.show();
}
