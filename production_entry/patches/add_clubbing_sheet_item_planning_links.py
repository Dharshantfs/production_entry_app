# -*- coding: utf-8 -*-
"""Add Planning Table / Planning Sheet links on Clubbing Sheet Item."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	if not frappe.db.exists("DocType", "Clubbing Sheet Item"):
		return

	fields = []
	meta = frappe.get_meta("Clubbing Sheet Item")
	for f in (
		{
			"fieldname": "custom_planning_table_row",
			"label": "Planning Table Row",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "party_code",
		},
		{
			"fieldname": "custom_planning_sheet",
			"label": "Planning Sheet",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "custom_planning_table_row",
		},
	):
		fn = f["fieldname"]
		if frappe.db.exists("Custom Field", {"dt": "Clubbing Sheet Item", "fieldname": fn}):
			continue
		if meta.has_field(fn):
			continue
		fields.append(f)

	if fields:
		create_custom_fields({"Clubbing Sheet Item": fields}, ignore_validate=True, update=False)
		frappe.clear_cache(doctype="Clubbing Sheet Item")

	frappe.db.commit()
