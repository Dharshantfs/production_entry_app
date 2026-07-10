# -*- coding: utf-8 -*-
"""Optional link from Shaft Production Run to Shift Mixing Sheet."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Shaft Production Run": [
				{
					"fieldname": "custom_shift_mixing_sheet",
					"label": "Shift Mixing Sheet",
					"fieldtype": "Link",
					"options": "Shift Mixing Sheet",
					"insert_after": "production_plan",
					"read_only": 1,
					"no_copy": 1,
				},
			],
		},
		ignore_validate=True,
		update=True,
	)
	frappe.clear_cache(doctype="Shaft Production Run")
	frappe.db.commit()
