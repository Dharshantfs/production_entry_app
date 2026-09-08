# -*- coding: utf-8 -*-
"""Add SPR child table for manual GSM View Patty Stock recycle (separate from automation)."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


PARENT_DT = "Shaft Production Run"
CHILD_DT = "GSM Manual Recycle Row"
FIELDNAME = "custom_gsm_manual_recycle_details"
SECTION = "section_gsm_manual_recycle"


def execute():
	if not frappe.db.exists("DocType", PARENT_DT):
		return

	# Ensure child DocType is synced from the app JSON.
	try:
		from frappe.modules.import_file import import_file_by_path
		import os

		app_path = frappe.get_app_path("production_entry")
		json_path = os.path.join(
			app_path,
			"production_planning",
			"doctype",
			"gsm_manual_recycle_row",
			"gsm_manual_recycle_row.json",
		)
		if os.path.exists(json_path):
			import_file_by_path(json_path, force=True, ignore_version=True, reset_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "ensure_spr_gsm_manual_recycle_table.import_child")

	if not frappe.db.exists("DocType", CHILD_DT):
		return

	fields = []
	meta = frappe.get_meta(PARENT_DT)
	if not meta.has_field(SECTION) and not frappe.db.exists(
		"Custom Field", {"dt": PARENT_DT, "fieldname": SECTION}
	):
		fields.append(
			{
				"fieldname": SECTION,
				"label": "GSM Manual Recycle (Patty Stock)",
				"fieldtype": "Section Break",
				"insert_after": "custom_recycled_wastage_details",
				"collapsible": 1,
			}
		)

	if not meta.has_field(FIELDNAME) and not frappe.db.exists(
		"Custom Field", {"dt": PARENT_DT, "fieldname": FIELDNAME}
	):
		fields.append(
			{
				"fieldname": FIELDNAME,
				"label": "GSM Manual Recycle Details",
				"fieldtype": "Table",
				"options": CHILD_DT,
				"insert_after": SECTION,
			}
		)

	if fields:
		create_custom_fields({PARENT_DT: fields}, update=True)

	frappe.clear_cache(doctype=PARENT_DT)
	frappe.clear_cache(doctype=CHILD_DT)
