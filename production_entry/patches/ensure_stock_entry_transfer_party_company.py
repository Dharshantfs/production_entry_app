# -*- coding: utf-8 -*-
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Company link for transfer STE when standard Party is Customer-only."""
	create_custom_fields(
		{
			"Stock Entry": [
				{
					"fieldname": "custom_transfer_to_company",
					"label": "Transfer To Company",
					"fieldtype": "Link",
					"options": "Company",
					"insert_after": "company",
					"read_only": 1,
				}
			]
		},
		ignore_validate=True,
		update=True,
	)
	frappe.db.commit()
