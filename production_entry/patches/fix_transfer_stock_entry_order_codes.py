# -*- coding: utf-8 -*-
"""Backfill order code on draft transfer Stock Entries from Transfer Approval lines."""


def execute():
	import frappe
	from frappe.utils import cint

	from production_entry.production_planning.transfer_logistics import (
		_ensure_stock_entry_order_codes,
		_order_codes_from_transfer_approval,
		_stock_entry_order_code_fieldname,
	)

	if not _stock_entry_order_code_fieldname():
		return

	for row in frappe.get_all(
		"Transfer Approval",
		filters={"status": "Approved", "stock_entry": ["is", "set"]},
		fields=["name", "stock_entry"],
	):
		ste = (row.stock_entry or "").strip()
		if not ste or not frappe.db.exists("Stock Entry", ste):
			continue
		if cint(frappe.db.get_value("Stock Entry", ste, "docstatus") or 0) != 0:
			continue
		try:
			ta = frappe.get_doc("Transfer Approval", row.name)
			codes = _order_codes_from_transfer_approval(ta)
			if codes:
				_ensure_stock_entry_order_codes(ste, codes)
		except Exception:
			pass
