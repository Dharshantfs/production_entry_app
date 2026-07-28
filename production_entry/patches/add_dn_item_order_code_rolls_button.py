# -*- coding: utf-8 -*-
"""Order Code + Rolls button on Delivery Note Item (for sites that already ran roll-fields patch)."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
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
	frappe.db.commit()
