# -*- coding: utf-8 -*-
"""Clubbing Sheet document hooks — stamp Planning Table on submit."""

from __future__ import annotations

import frappe
from frappe.utils import cint, cstr


def clubbing_sheet_before_submit(doc, method=None):
	"""Require Trip ID; stamp club ID + loading sequence onto Planning Despatch rows."""
	if not cstr(doc.get("trip_id") or "").strip():
		frappe.throw("Please enter a Trip ID before submitting the Clubbing Sheet.")

	if not doc.get("items"):
		return

	has_pt_club = frappe.db.has_column("Planning Table", "custom_clubbing_sheet")
	has_psi_club = frappe.db.has_column("Planning sheet Item", "custom_clubbing_sheet")
	if not has_pt_club and not has_psi_club:
		frappe.msgprint(
			"Planning club fields missing — run bench migrate (custom_clubbing_sheet).",
			indicator="orange",
			alert=True,
		)
		return

	for item in doc.items:
		party = cstr(item.get("party_code") or "").strip()
		so = cstr(item.get("sales_order") or "").strip()
		seq = cstr(item.get("loading_sequence") or "").strip()
		load_order = cint(item.get("idx") or 0)
		planning_sheet = cstr(item.get("planning_sheet") or item.get("custom_planning_sheet") or "").strip()
		ptr = cstr(item.get("planning_table_row") or item.get("custom_planning_table_row") or "").strip()

		matches = _find_despatch_pt_rows(
			planning_sheet=planning_sheet,
			sales_order=so,
			party_code=party,
			planning_table_row=ptr,
			club_name=doc.name,
		)
		for m in matches:
			_stamp_pt(m.pt_name, doc.name, seq, load_order, has_pt_club)
			if has_psi_club:
				_stamp_psi_for_parent(m.parent, doc.name, seq, load_order)


def _find_despatch_pt_rows(planning_sheet="", sales_order="", party_code="", planning_table_row="", club_name=""):
	if planning_table_row and frappe.db.exists("Planning Table", planning_table_row):
		parent = frappe.db.get_value("Planning Table", planning_table_row, "parent")
		return [frappe._dict(pt_name=planning_table_row, parent=parent)]

	sql = """
		select pt.name as pt_name, pt.parent
		from `tabPlanning Table` pt
		inner join `tabPlanning sheet` ps on ps.name = pt.parent
		where ifnull(pt.custom_movement_type, '') = 'Despatch'
		  and ifnull(ps.docstatus, 0) < 2
	"""
	args = {}
	if planning_sheet:
		sql += " and ps.name = %(ps)s"
		args["ps"] = planning_sheet
	elif sales_order:
		sql += " and ps.sales_order = %(so)s"
		args["so"] = sales_order
	elif party_code:
		sql += " and ps.party_code = %(party)s"
		args["party"] = party_code
	else:
		return []

	if frappe.db.has_column("Planning Table", "custom_clubbing_sheet"):
		sql += """
		  and (
		    ifnull(pt.custom_clubbing_sheet, '') = ''
		    or pt.custom_clubbing_sheet = %(club)s
		  )
		"""
		args["club"] = club_name or ""

	if frappe.db.has_column("Planning Table", "custom_despatch_status"):
		sql += """
		  and ifnull(pt.custom_despatch_status, '') not in
		      ('Despatched', 'Approved', 'Pending Approval')
		"""

	return frappe.db.sql(sql, args, as_dict=True) or []


def _stamp_pt(pt_name, club_name, seq, load_order, has_pt_club):
	if not has_pt_club:
		return
	vals = {"custom_clubbing_sheet": club_name}
	if frappe.db.has_column("Planning Table", "custom_loading_sequence"):
		vals["custom_loading_sequence"] = seq
	if frappe.db.has_column("Planning Table", "custom_club_load_order"):
		vals["custom_club_load_order"] = load_order
	frappe.db.set_value("Planning Table", pt_name, vals, update_modified=False)


def _stamp_psi_for_parent(parent, club_name, seq, load_order):
	psi_rows = frappe.db.sql(
		"""
		select name from `tabPlanning sheet Item`
		where parent = %s and ifnull(custom_movement_type, '') = 'Despatch'
		""",
		parent,
		as_dict=True,
	)
	for p in psi_rows or []:
		pvals = {"custom_clubbing_sheet": club_name}
		if frappe.db.has_column("Planning sheet Item", "custom_loading_sequence"):
			pvals["custom_loading_sequence"] = seq
		if frappe.db.has_column("Planning sheet Item", "custom_club_load_order"):
			pvals["custom_club_load_order"] = load_order
		frappe.db.set_value("Planning sheet Item", p.name, pvals, update_modified=False)
