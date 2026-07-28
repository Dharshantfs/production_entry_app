# -*- coding: utf-8 -*-
"""Remove duplicate broken Rolls button (custom_rolls) on Delivery Note Item.

Keep only custom_despatch_rolls which opens the despatch roll list dialog.
Also show Serial and Batch Bundle in the items grid so multi-batch despatch is visible
(Batch No stays empty by design when using a bundle).
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
	# Delete site custom field custom_rolls (duplicate broken Rolls button)
	for cf_name in (
		"Delivery Note Item-custom_rolls",
		"Delivery Note Item-rolls",
	):
		if frappe.db.exists("Custom Field", cf_name):
			frappe.delete_doc("Custom Field", cf_name, force=1, ignore_permissions=True)

	# Also catch any Custom Field on DN Item labeled Rolls with wrong fieldname
	extras = frappe.get_all(
		"Custom Field",
		filters={
			"dt": "Delivery Note Item",
			"fieldname": ("in", ["custom_rolls", "rolls"]),
		},
		pluck="name",
	)
	for name in extras or []:
		frappe.delete_doc("Custom Field", name, force=1, ignore_permissions=True)

	# Ensure the working Rolls button + Order Code exist
	create_custom_fields(
		{
			"Delivery Note Item": [
				{
					"fieldname": "custom_order_code",
					"label": "Order Code",
					"fieldtype": "Data",
					"insert_after": "item_code",
					"read_only": 1,
					"in_list_view": 1,
					"columns": 1,
				},
				{
					"fieldname": "custom_despatch_rolls",
					"label": "Rolls",
					"fieldtype": "Button",
					"insert_after": "qty",
					"in_list_view": 1,
				},
			],
		},
		ignore_validate=True,
		update=True,
	)

	# Show Serial and Batch Bundle in grid (batches live here, not in Batch No)
	if frappe.db.has_column("Delivery Note Item", "serial_and_batch_bundle"):
		make_property_setter(
			"Delivery Note Item",
			"serial_and_batch_bundle",
			"in_list_view",
			1,
			"Check",
			validate_fields_for_doctype=False,
		)
		make_property_setter(
			"Delivery Note Item",
			"batch_no",
			"in_list_view",
			0,
			"Check",
			validate_fields_for_doctype=False,
		)

	frappe.clear_cache(doctype="Delivery Note Item")
	frappe.db.commit()
