"""Ensure Batch.custom_produced_bagpcs exists for Is Bag SPR batch sync."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	if not frappe.db.table_exists("Batch"):
		return
	fields = {
		"Batch": [
			{
				"fieldname": "custom_produced_bagpcs",
				"label": "Produced Bag PCS",
				"fieldtype": "Float",
				"insert_after": "batch_qty",
				"precision": 0,
				"read_only": 0,
			}
		]
	}
	create_custom_fields(fields, update=True)
	frappe.clear_cache(doctype="Batch")
	frappe.db.commit()
