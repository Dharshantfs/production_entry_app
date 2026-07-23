# -*- coding: utf-8 -*-
"""Add Clubbing Sheet ID + loading sequence + load order on planning / despatch docs.

Additive only. Site Clubbing Sheet scripts stamp these on submit; despatch reads them.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def _club_link_or_data():
	if frappe.db.exists("DocType", "Clubbing Sheet"):
		return "Link", "Clubbing Sheet"
	return "Data", ""


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
	ft, opts = _club_link_or_data()
	club_field = {
		"fieldname": "custom_clubbing_sheet",
		"label": "Clubbing Sheet ID",
		"fieldtype": ft,
		"read_only": 1,
		"in_list_view": 1,
	}
	if opts:
		club_field["options"] = opts

	seq_field = {
		"fieldname": "custom_loading_sequence",
		"label": "Loading Sequence",
		"fieldtype": "Data",
		"read_only": 1,
		"in_list_view": 1,
	}
	order_field = {
		"fieldname": "custom_club_load_order",
		"label": "Club Load Order",
		"fieldtype": "Int",
		"read_only": 1,
		"default": "0",
	}

	for dt in ("Planning Table", "Planning sheet Item"):
		club = dict(club_field)
		seq = dict(seq_field)
		ordf = dict(order_field)
		club["insert_after"] = "custom_despatch_approval"
		seq["insert_after"] = "custom_clubbing_sheet"
		ordf["insert_after"] = "custom_loading_sequence"
		_ensure_fields(dt, [club, seq, ordf])

	# Despatch Approval header
	da_club = dict(club_field)
	da_club["read_only"] = 0
	da_club["insert_after"] = "from_company"
	da_notes = {
		"fieldname": "custom_delivery_notes",
		"label": "Delivery Notes (JSON)",
		"fieldtype": "Small Text",
		"read_only": 1,
		"insert_after": "delivery_note",
	}
	_ensure_fields("Despatch Approval", [da_club, da_notes])

	# Despatch Approval Line — sequence + scan
	_ensure_fields(
		"Despatch Approval Line",
		[
			{
				"fieldname": "custom_loading_sequence",
				"label": "Loading Sequence",
				"fieldtype": "Data",
				"insert_after": "party_code",
				"in_list_view": 1,
			},
			{
				"fieldname": "custom_club_load_order",
				"label": "Club Load Order",
				"fieldtype": "Int",
				"default": "0",
				"insert_after": "custom_loading_sequence",
			},
			{
				"fieldname": "custom_scanned",
				"label": "Scanned",
				"fieldtype": "Check",
				"default": "0",
				"insert_after": "batch_no",
				"in_list_view": 1,
			},
		],
	)

	frappe.db.commit()
