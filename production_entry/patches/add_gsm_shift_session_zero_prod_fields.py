# -*- coding: utf-8 -*-
"""GSM Shift Session — zero-production close flag and batch reuse audit link."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"GSM Shift Session": [
				{
					"fieldname": "zero_production_close",
					"label": "Zero Production Close",
					"fieldtype": "Check",
					"insert_after": "batch_series_prefix",
					"read_only": 1,
				},
				{
					"fieldname": "reused_from_session",
					"label": "Reused From Session",
					"fieldtype": "Link",
					"options": "GSM Shift Session",
					"insert_after": "previous_session",
					"read_only": 1,
				},
			],
		},
		ignore_validate=True,
		update=True,
	)
	frappe.clear_cache(doctype="GSM Shift Session")
	frappe.db.commit()
