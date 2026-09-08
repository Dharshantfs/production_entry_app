# -*- coding: utf-8 -*-
"""Hide Clubbing Sheet Item.view_rolls — weight + no of rolls are enough."""

from __future__ import annotations

import frappe


def execute():
	dt = "Clubbing Sheet Item"
	fn = "view_rolls"
	if not frappe.db.exists("DocType", dt):
		return
	df = frappe.db.get_value("DocField", {"parent": dt, "fieldname": fn}, "name")
	if df:
		frappe.db.set_value("DocField", df, {"hidden": 1, "in_list_view": 0}, update_modified=False)
	cf = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fn}, "name")
	if cf:
		frappe.db.set_value("Custom Field", cf, {"hidden": 1, "in_list_view": 0}, update_modified=False)
	frappe.clear_cache(doctype=dt)
	frappe.clear_cache(doctype="Clubbing Sheet")
