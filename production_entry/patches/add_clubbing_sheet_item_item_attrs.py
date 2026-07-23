# -*- coding: utf-8 -*-
"""Add quality / color / gsm / planned_date on Clubbing Sheet Item for planners."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	if not frappe.db.exists("DocType", "Clubbing Sheet Item"):
		return

	meta = frappe.get_meta("Clubbing Sheet Item")
	wanted = [
		{
			"fieldname": "custom_quality",
			"label": "Quality",
			"fieldtype": "Data",
			"read_only": 1,
			"in_list_view": 1,
			"insert_after": "party_code",
		},
		{
			"fieldname": "custom_color",
			"label": "Color",
			"fieldtype": "Data",
			"read_only": 1,
			"in_list_view": 1,
			"insert_after": "custom_quality",
		},
		{
			"fieldname": "custom_gsm",
			"label": "GSM",
			"fieldtype": "Float",
			"read_only": 1,
			"in_list_view": 1,
			"insert_after": "custom_color",
		},
		{
			"fieldname": "custom_planned_date",
			"label": "Planned Date",
			"fieldtype": "Date",
			"read_only": 1,
			"in_list_view": 1,
			"insert_after": "custom_gsm",
		},
		{
			"fieldname": "custom_planning_table_row",
			"label": "Planning Table Row",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "custom_planned_date",
		},
		{
			"fieldname": "custom_planning_sheet",
			"label": "Planning Sheet",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "custom_planning_table_row",
		},
	]
	fields = []
	for f in wanted:
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
