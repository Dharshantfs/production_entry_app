# -*- coding: utf-8 -*-
"""Show custom_running_patty_wastage on Is Bag SPR (undo bag-only hide)."""

import frappe


def execute():
	doctype = "Shaft Production Run"
	fieldname = "custom_running_patty_wastage"
	cf_name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname})
	if not cf_name:
		return
	try:
		frappe.db.set_value("Custom Field", cf_name, "depends_on", "", update_modified=False)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "show_spr_patty_wastage_for_bag")
	frappe.clear_cache(doctype=doctype)
	frappe.db.commit()
