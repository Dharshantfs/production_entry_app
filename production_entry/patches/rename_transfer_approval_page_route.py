# -*- coding: utf-8 -*-
"""Page route transfer-approval conflicts with Transfer Approval DocType list."""
import frappe


def execute():
	old = "transfer-approval"
	new = "transfer-approval-dashboard"
	if frappe.db.exists("Page", old) and not frappe.db.exists("Page", new):
		frappe.rename_doc("Page", old, new, force=1, merge=0)
	elif frappe.db.exists("Page", new):
		doc = frappe.get_doc("Page", new)
		doc.page_name = new
		doc.title = doc.title or "Transfer Approval"
		doc.save(ignore_permissions=True)
	frappe.db.commit()
