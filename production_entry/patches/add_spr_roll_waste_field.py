# -*- coding: utf-8 -*-
"""Add custom_roll_waste child table on Shaft Production Run (mirror Running Patty Wastage)."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	if frappe.db.exists("DocType", "Roll Waste Row"):
		frappe.reload_doc("production_planning", "doctype", "roll_waste_row")

	insert_after = "items"
	if frappe.get_meta("Shaft Production Run", cached=False).has_field("custom_recycled_wastage_details"):
		insert_after = "custom_recycled_wastage_details"
	elif frappe.get_meta("Shaft Production Run", cached=False).has_field("custom_running_patty_wastage"):
		insert_after = "custom_running_patty_wastage"

	if not frappe.get_meta("Shaft Production Run", cached=False).has_field("custom_roll_waste"):
		create_custom_fields(
			{
				"Shaft Production Run": [
					{
						"fieldname": "custom_roll_waste",
						"label": "Roll Waste",
						"fieldtype": "Table",
						"options": "Roll Waste Row",
						"insert_after": insert_after,
					}
				]
			},
			ignore_validate=True,
			update=True,
		)
		frappe.clear_cache(doctype="Shaft Production Run")
	frappe.db.commit()
