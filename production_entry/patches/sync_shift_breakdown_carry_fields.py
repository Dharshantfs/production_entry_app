# -*- coding: utf-8 -*-
"""Add Shift Breakdown machine_status fields and backfill Open/Off rows."""

import frappe


def execute():
	frappe.reload_doc("production_planning", "doctype", "shift_breakdown_row")
	frappe.reload_doc("production_planning", "doctype", "shift_breakdown")
	if not frappe.db.exists("DocType", "Shift Breakdown"):
		return
	if not frappe.db.has_column("Shift Breakdown", "machine_status"):
		return
	names = frappe.get_all("Shift Breakdown", pluck="name")
	for name in names:
		doc = frappe.get_doc("Shift Breakdown", name)
		doc.sync_machine_status()
		updates = {
			"machine_status": doc.machine_status or "On",
			"last_reason": doc.last_reason or "",
			"open_since": doc.open_since,
		}
		frappe.db.set_value("Shift Breakdown", name, updates, update_modified=False)
		if frappe.db.has_column("Shift Breakdown Row", "row_status"):
			for row in doc.breakdowns or []:
				status = "Open" if not row.on_time else "Closed"
				frappe.db.set_value("Shift Breakdown Row", row.name, "row_status", status, update_modified=False)
