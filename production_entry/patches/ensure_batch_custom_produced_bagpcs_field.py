"""Ensure Batch.custom_produced_bagpcs exists for Is Bag SPR batch sync.

Never change fieldtype on an existing Custom Field — sites may already have Data.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	if not frappe.db.table_exists("Batch"):
		return
	existing = frappe.db.get_value(
		"Custom Field",
		{"dt": "Batch", "fieldname": "custom_produced_bagpcs"},
		["name", "fieldtype"],
		as_dict=True,
	)
	if existing:
		# Field already on site (often Data) — do not attempt Data→Float conversion.
		return
	fields = {
		"Batch": [
			{
				"fieldname": "custom_produced_bagpcs",
				"label": "Produced Bag PCS",
				"fieldtype": "Data",
				"insert_after": "batch_qty",
				"read_only": 0,
			}
		]
	}
	create_custom_fields(fields, update=False)
	frappe.clear_cache(doctype="Batch")
	frappe.db.commit()
