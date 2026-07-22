"""Ensure Shaft Production Run Item.custom_bay (Link → Warehouse Bay) exists.

Additive only: if the field already exists (Customize Form or prior patch), do nothing.
Never changes type/options of an existing custom_bay field.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	dt = "Shaft Production Run Item"
	if not frappe.db.exists("DocType", dt):
		return

	# Already present as Custom Field — leave untouched
	if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": "custom_bay"}):
		return

	# Already present as standard DocField — leave untouched
	try:
		meta = frappe.get_meta(dt)
		if meta.has_field("custom_bay"):
			return
	except Exception:
		pass

	insert_after = "job"
	try:
		meta = frappe.get_meta(dt)
		for candidate in (
			"custom_cbm_cubic_meters",
			"custom_cbm",
			"custom_produced_bagpcs",
			"custom_achieved_bag_pcs",
			"net_weight",
		):
			if meta.has_field(candidate):
				insert_after = candidate
				break
	except Exception:
		pass

	# Only create when Warehouse Bay exists (WMS installed); otherwise skip safely
	options = "Warehouse Bay" if frappe.db.exists("DocType", "Warehouse Bay") else ""
	field_def = {
		"fieldname": "custom_bay",
		"label": "Bay",
		"fieldtype": "Link" if options else "Data",
		"insert_after": insert_after,
		"in_list_view": 1,
	}
	if options:
		field_def["options"] = options

	create_custom_fields({dt: [field_def]}, update=False)
	frappe.clear_cache(doctype=dt)
	frappe.db.commit()
