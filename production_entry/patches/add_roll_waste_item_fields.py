# -*- coding: utf-8 -*-
"""Add item_code and item_name to Roll Waste Row child table."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Roll Waste Row": [
				{
					"fieldname": "item_code",
					"label": "Item Code",
					"fieldtype": "Link",
					"options": "Item",
					"insert_after": "job_id",
					"in_list_view": 1,
				},
				{
					"fieldname": "item_name",
					"label": "Item Name",
					"fieldtype": "Data",
					"fetch_from": "item_code.item_name",
					"insert_after": "item_code",
					"in_list_view": 1,
					"read_only": 1,
				},
			],
		},
		ignore_validate=True,
		update=True,
	)
	frappe.clear_cache(doctype="Roll Waste Row")
	frappe.db.commit()
