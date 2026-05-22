# -*- coding: utf-8 -*-
"""Remove duplicate Custom Field when nature_of_processing exists on the DocType."""
import frappe


def execute():
	if not frappe.db.exists("DocType", "Transfer Approval"):
		return
	meta = frappe.get_meta("Transfer Approval", cached=False)
	if not meta.has_field("nature_of_processing"):
		return
	# Standard DocField present — drop duplicate Custom Field row if any.
	cf_name = frappe.db.get_value(
		"Custom Field",
		{"dt": "Transfer Approval", "fieldname": "nature_of_processing", "is_system_generated": 0},
		"name",
	)
	if cf_name:
		try:
			frappe.delete_doc("Custom Field", cf_name, force=1, ignore_permissions=True)
		except Exception:
			pass
	frappe.clear_cache(doctype="Transfer Approval")
	frappe.db.commit()
