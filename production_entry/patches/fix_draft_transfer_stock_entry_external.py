# -*- coding: utf-8 -*-
"""Set External Transfer on existing draft transfer Stock Entries from approved Transfer Approval."""


def execute():
	import frappe
	from frappe.utils import cint

	from production_entry.production_planning.transfer_logistics import (
		_ensure_stock_entry_external_transfer,
		_stock_entry_external_transfer_fieldname,
	)

	if not _stock_entry_external_transfer_fieldname():
		return

	for row in frappe.get_all(
		"Transfer Approval",
		filters={"status": "Approved", "stock_entry": ["is", "set"]},
		fields=["stock_entry"],
	):
		ste = (row.stock_entry or "").strip()
		if not ste or not frappe.db.exists("Stock Entry", ste):
			continue
		if cint(frappe.db.get_value("Stock Entry", ste, "docstatus") or 0) != 0:
			continue
		_ensure_stock_entry_external_transfer(ste, 1)
		if frappe.db.has_column("Stock Entry", "add_to_transit"):
			frappe.db.set_value("Stock Entry", ste, "add_to_transit", 1, update_modified=False)
