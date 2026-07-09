# -*- coding: utf-8 -*-
"""No. of Shaft on SPR roll lines — which shaft produced each roll."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Shaft Production Run Item": [
				{
					"fieldname": "custom_no_of_shaft",
					"label": "No. of Shaft",
					"fieldtype": "Int",
					"insert_after": "job",
					"in_list_view": 1,
					"columns": 2,
				}
			],
		},
		ignore_validate=True,
		update=True,
	)
	frappe.clear_cache(doctype="Shaft Production Run Item")
	frappe.db.commit()
