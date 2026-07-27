# -*- coding: utf-8 -*-
"""Allow planners to override loading sequence — skip auto-recalc on save when locked."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	if not frappe.db.exists("DocType", "Clubbing Sheet"):
		return

	if frappe.db.exists("Custom Field", {"dt": "Clubbing Sheet", "fieldname": "custom_lock_loading_sequence"}):
		return

	create_custom_fields(
		{
			"Clubbing Sheet": [
				{
					"fieldname": "custom_lock_loading_sequence",
					"label": "Lock Loading Sequence",
					"fieldtype": "Check",
					"default": "0",
					"hidden": 1,
					"insert_after": "load_type",
					"description": "Set when user manually edits loading sequence; before_save skips auto assignment.",
				}
			]
		},
		ignore_validate=True,
		update=False,
	)
	frappe.clear_cache(doctype="Clubbing Sheet")
