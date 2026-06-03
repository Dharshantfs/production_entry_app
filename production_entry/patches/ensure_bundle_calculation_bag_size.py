"""Ensure Bundle Calculation child table has bag_size column (SPR box-bag)."""

import frappe


def execute():
	if not frappe.db.table_exists("Bundle Calculation"):
		return
	if not frappe.db.has_column("Bundle Calculation", "bag_size"):
		frappe.db.sql(
			"""
			ALTER TABLE `tabBundle Calculation`
			ADD COLUMN `bag_size` varchar(140)
			"""
		)
		frappe.db.commit()
