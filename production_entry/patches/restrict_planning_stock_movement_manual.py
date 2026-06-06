# -*- coding: utf-8 -*-
"""Stock movement is set only via Check Stock — not from the grid dropdown."""

import frappe


def execute():
	opts = "Despatch\nTransfer"
	for dt in ("Planning Table", "Planning sheet Item"):
		cf = frappe.db.get_value(
			"Custom Field",
			{"dt": dt, "fieldname": "custom_movement_type"},
			"name",
		)
		if cf:
			frappe.db.set_value("Custom Field", cf, "options", opts, update_modified=False)
	frappe.clear_cache(doctype="Planning Table")
	frappe.clear_cache(doctype="Planning sheet Item")
	frappe.db.commit()
