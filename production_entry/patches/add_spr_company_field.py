# -*- coding: utf-8 -*-
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Expose Production Plan / Work Order company on Shaft Production Run."""
	if not frappe.get_meta("Shaft Production Run", cached=False).has_field("company"):
		create_custom_fields(
			{
				"Shaft Production Run": [
					{
						"fieldname": "company",
						"label": "Company",
						"fieldtype": "Link",
						"options": "Company",
						"insert_after": "production_plan",
						"read_only": 1,
						"in_list_view": 1,
					}
				]
			},
			ignore_validate=True,
			update=True,
		)
		frappe.clear_cache(doctype="Shaft Production Run")
	if frappe.db.has_column("Shaft Production Run", "company"):
		frappe.db.sql(
			"""
			UPDATE `tabShaft Production Run` spr
			INNER JOIN `tabProduction Plan` pp ON pp.name = spr.production_plan
			SET spr.company = pp.company
			WHERE IFNULL(spr.company, '') = ''
			  AND IFNULL(spr.production_plan, '') != ''
			  AND IFNULL(pp.company, '') != ''
			"""
		)
	frappe.db.commit()
