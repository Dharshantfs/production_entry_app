"""Add custom_bag_size on Shaft Production Run Item; migrate bag data off custom_sheet_size."""

import frappe


def execute():
	child = "Shaft Production Run Item"
	if not frappe.db.table_exists(child):
		return
	if not frappe.db.has_column(child, "custom_bag_size"):
		frappe.db.sql(
			f"""
			ALTER TABLE `tab{child}`
			ADD COLUMN `custom_bag_size` varchar(140)
			"""
		)
	if frappe.db.has_column(child, "custom_sheet_size") and frappe.db.has_column(
		"Shaft Production Run", "custom_is_box_bag"
	):
		frappe.db.sql(
			"""
			UPDATE `tabShaft Production Run Item` spi
			INNER JOIN `tabShaft Production Run` spr ON spr.name = spi.parent
			SET spi.custom_bag_size = spi.custom_sheet_size,
			    spi.custom_sheet_size = NULL
			WHERE IFNULL(spr.custom_is_box_bag, 0) = 1
			  AND IFNULL(spi.custom_bag_size, '') = ''
			  AND IFNULL(spi.custom_sheet_size, '') != ''
			"""
		)
	frappe.clear_cache(doctype=child)
	frappe.db.commit()
