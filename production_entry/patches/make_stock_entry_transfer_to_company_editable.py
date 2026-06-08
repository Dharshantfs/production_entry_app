# -*- coding: utf-8 -*-
import frappe


def execute():
	"""Manual Stock Entry: Transfer To Company should be editable (not locked to logistics auto-fill)."""
	for fieldname in ("custom_transfer_to_company",):
		name = frappe.db.get_value(
			"Custom Field",
			{"dt": "Stock Entry", "fieldname": fieldname},
			"name",
		)
		if name:
			frappe.db.set_value("Custom Field", name, "read_only", 0, update_modified=False)
	frappe.db.commit()
