# -*- coding: utf-8 -*-
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Transfer Approval": [
				{
					"fieldname": "custom_logistics_queue_idx",
					"label": "Logistics Queue",
					"fieldtype": "Int",
					"default": "0",
					"insert_after": "stock_entry",
					"read_only": 1,
				}
			]
		},
		ignore_validate=True,
		update=True,
	)
	frappe.db.commit()
