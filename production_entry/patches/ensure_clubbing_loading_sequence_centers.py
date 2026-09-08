# -*- coding: utf-8 -*-
"""Ensure Clubbing Sheet Item.loading_sequence Select options include Center 1–10."""

from __future__ import annotations

import frappe

DT = "Clubbing Sheet Item"
FIELD = "loading_sequence"
OPTIONS = "\n".join(
	[
		"Inside",
		"Center 1",
		"Center 2",
		"Center 3",
		"Center 4",
		"Center 5",
		"Center 6",
		"Center 7",
		"Center 8",
		"Center 9",
		"Center 10",
		"Outside",
		"Full Load",
	]
)


def execute():
	if not frappe.db.exists("DocType", DT):
		return

	# Prefer DocField; fall back to Custom Field
	df_name = frappe.db.get_value("DocField", {"parent": DT, "fieldname": FIELD}, "name")
	if df_name:
		frappe.db.set_value("DocField", df_name, "options", OPTIONS, update_modified=False)
	else:
		cf_name = frappe.db.get_value("Custom Field", {"dt": DT, "fieldname": FIELD}, "name")
		if cf_name:
			frappe.db.set_value("Custom Field", cf_name, "options", OPTIONS, update_modified=False)

	frappe.clear_cache(doctype=DT)
	frappe.clear_cache(doctype="Clubbing Sheet")
