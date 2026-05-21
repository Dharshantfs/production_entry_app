# -*- coding: utf-8 -*-
"""Rename movement type Transport → Transfer on planning child rows."""


def execute():
	import frappe

	field = "custom_movement_type"
	for dt in ("Planning Table", "Planning sheet Item"):
		if not frappe.db.table_exists(dt) or not frappe.db.has_column(dt, field):
			continue
		frappe.db.sql(
			f"""
			UPDATE `tab{dt}`
			SET `{field}` = %s
			WHERE `{field}` = %s
			""",
			("Transfer", "Transport"),
		)
