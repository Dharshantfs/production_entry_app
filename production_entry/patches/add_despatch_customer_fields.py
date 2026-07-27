# -*- coding: utf-8 -*-
"""Despatch Customer fields for Clubbing → Planning → Despatch → DN.

Club ID still stamps on the order-giver Planning Table rows.
Despatch Customer is who the DN is for (may differ from Planning/SO customer).
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def _ensure_fields(dt, fields):
	if not frappe.db.exists("DocType", dt):
		return
	to_create = []
	meta = None
	try:
		meta = frappe.get_meta(dt)
	except Exception:
		pass
	for f in fields:
		fn = f["fieldname"]
		if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fn}):
			continue
		if meta and meta.has_field(fn):
			continue
		to_create.append(f)
	if to_create:
		create_custom_fields({dt: to_create}, ignore_validate=True, update=False)
		frappe.clear_cache(doctype=dt)


def execute():
	# Clubbing Sheet Item — editable override
	_ensure_fields(
		"Clubbing Sheet Item",
		[
			{
				"fieldname": "custom_despatch_customer",
				"label": "Despatch Customer",
				"fieldtype": "Link",
				"options": "Customer",
				"in_list_view": 1,
				"insert_after": "customer",
				"description": "Who receives the DN. Defaults from Planning/SO; change for emergency reallocation.",
			},
			{
				"fieldname": "custom_despatch_sales_order",
				"label": "Despatch Sales Order",
				"fieldtype": "Link",
				"options": "Sales Order",
				"insert_after": "custom_despatch_customer",
				"description": "Optional. Link only if Despatch Customer has their own SO. Leave blank to skip SO link.",
			},
		],
	)

	# Planning Table — stamped on Clubbing submit (display / carry to despatch)
	_ensure_fields(
		"Planning Table",
		[
			{
				"fieldname": "custom_despatch_customer",
				"label": "Despatch Customer",
				"fieldtype": "Link",
				"options": "Customer",
				"read_only": 1,
				"insert_after": "custom_clubbing_sheet",
			},
			{
				"fieldname": "custom_despatch_sales_order",
				"label": "Despatch Sales Order",
				"fieldtype": "Link",
				"options": "Sales Order",
				"read_only": 1,
				"insert_after": "custom_despatch_customer",
			},
		],
	)

	# Despatch Approval Line — used when building DN
	_ensure_fields(
		"Despatch Approval Line",
		[
			{
				"fieldname": "custom_despatch_customer",
				"label": "Despatch Customer",
				"fieldtype": "Link",
				"options": "Customer",
				"insert_after": "customer_name",
			},
			{
				"fieldname": "custom_despatch_sales_order",
				"label": "Despatch Sales Order",
				"fieldtype": "Link",
				"options": "Sales Order",
				"insert_after": "custom_despatch_customer",
			},
		],
	)

	frappe.db.commit()
