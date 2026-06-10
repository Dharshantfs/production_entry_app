# -*- coding: utf-8 -*-
"""Remove the site Custom Field that duplicates the standard `customer` field on Shaft Production Run.

The DocType JSON ships a `customer` Link field; a Customize Form copy
(`custom_customer` or a Custom Field row named `customer`) renders the field twice.
Data is copied into the standard column before the duplicate is deleted.
"""
import frappe


def execute():
	doctype = "Shaft Production Run"

	# Backfill standard column from the duplicate before dropping it.
	if frappe.db.has_column(doctype, "customer") and frappe.db.has_column(doctype, "custom_customer"):
		frappe.db.sql(
			"""
			UPDATE `tabShaft Production Run`
			SET customer = custom_customer
			WHERE IFNULL(customer, '') = ''
			  AND IFNULL(custom_customer, '') != ''
			"""
		)

	for fieldname in ("custom_customer", "customer"):
		for row in frappe.get_all(
			"Custom Field",
			filters={"dt": doctype, "fieldname": fieldname},
			fields=["name"],
		):
			try:
				frappe.delete_doc("Custom Field", row.name, force=1)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"remove_spr_dup_customer: {fieldname}")

	frappe.clear_cache(doctype=doctype)
	frappe.db.commit()
