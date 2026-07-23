# -*- coding: utf-8 -*-
"""Delivery Note creation from Despatch Approval."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate

from production_entry.production_planning.despatch_logistics import _cstr, _fg_warehouse_for_company, _resolve_customer


def build_delivery_note_from_despatch(despatch_approval, party_code=None):
	"""Build Delivery Note doc (not saved) from approved despatch lines.

	If party_code is set (including empty string), only matching order lines are included.
	If party_code is None, all lines are included (legacy single-DN path).
	"""
	da = despatch_approval
	if isinstance(da, str):
		da = frappe.get_doc("Despatch Approval", da)
	if not da.lines:
		frappe.throw(_("Despatch Approval has no lines."))

	fc = _cstr(da.from_company)
	wh = _fg_warehouse_for_company(fc)
	if not wh:
		frappe.throw(_("No finished-goods warehouse configured for {0}.").format(fc))

	use_filter = party_code is not None
	pc_filter = _cstr(party_code) if use_filter else None
	lines = []
	for ln in da.lines or []:
		if use_filter and _cstr(ln.party_code) != pc_filter:
			continue
		lines.append(ln)
	if not lines:
		frappe.throw(_("No despatch lines for order {0}.").format(pc_filter if use_filter else "—"))

	customer = ""
	for ln in lines:
		customer = _resolve_customer(ln.customer_name)
		if customer:
			break
	if not customer:
		frappe.throw(_("Could not resolve Customer from despatch lines. Link a valid customer name."))

	dn = frappe.new_doc("Delivery Note")
	dn.company = fc
	dn.customer = customer
	dn.set_posting_time = 1
	dn.posting_date = getdate()
	dn.set_warehouse = wh

	for ln in lines:
		qty = flt(ln.qty) or flt(ln.net_weight)
		if qty <= 0:
			continue
		row = {
			"item_code": ln.item_code,
			"qty": qty,
			"uom": ln.uom or frappe.db.get_value("Item", ln.item_code, "stock_uom") or "Kg",
			"warehouse": wh,
			"against_sales_order": "",
		}
		if ln.batch_no and frappe.db.get_value("Item", ln.item_code, "has_batch_no"):
			row["batch_no"] = ln.batch_no
		if frappe.db.has_column("Delivery Note Item", "use_serial_batch_fields"):
			row["use_serial_batch_fields"] = 1 if ln.batch_no else 0
		dn.append("items", row)

	if not dn.items:
		frappe.throw(_("No delivery lines to create."))
	return dn


def create_draft_delivery_notes_by_order(despatch_approval):
	"""Insert one draft Delivery Note per distinct party_code on the approval."""
	da = despatch_approval
	if isinstance(da, str):
		da = frappe.get_doc("Despatch Approval", da)

	order_keys = []
	seen = set()
	for ln in da.lines or []:
		pc = _cstr(ln.party_code)
		if pc in seen:
			continue
		seen.add(pc)
		order_keys.append(pc)

	names = []
	for pc in order_keys:
		dn = build_delivery_note_from_despatch(da, party_code=pc)
		dn.insert(ignore_permissions=True)
		names.append(dn.name)
	return names


def make_delivery_note_from_despatch(despatch_approval):
	"""Insert draft Delivery Note (legacy auto-create path)."""
	dn = build_delivery_note_from_despatch(despatch_approval)
	dn.insert(ignore_permissions=True)
	return dn.name
