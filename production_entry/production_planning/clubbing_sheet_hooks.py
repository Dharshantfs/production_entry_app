# -*- coding: utf-8 -*-
"""Clubbing Sheet document hooks — stamp / clear Planning Table club fields."""

from __future__ import annotations

import frappe
from frappe.utils import cint, cstr, flt


def clubbing_sheet_before_submit(doc, method=None):
	"""Require Trip ID; stamp only the selected Planning Table Despatch rows."""
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

	missing = []
	for item in doc.items:
		seq = cstr(item.get("loading_sequence") or "").strip()
		load_order = cint(item.get("idx") or 0)
		ptr = cstr(item.get("planning_table_row") or item.get("custom_planning_table_row") or "").strip()

		matches = _resolve_pt_rows_for_item(item, club_name=doc.name)
		if not matches:
			label = cstr(item.get("party_code") or item.get("sales_order") or item.idx)
			missing.append(f"row {item.idx} ({label})")
			continue

		for m in matches:
			_stamp_pt(m.pt_name, doc.name, seq, load_order, has_pt_club)
			if has_psi_club:
				_stamp_psi_matching_pt(m.pt_name, m.parent, doc.name, seq, load_order)

	if missing:
		frappe.throw(
			"Could not map Clubbing items to Planning Table rows: "
			+ ", ".join(missing)
			+ ". Use Get Sales Orders again so each line stores Planning Table Row."
		)


def clubbing_sheet_on_cancel(doc, method=None):
	"""Clear club ID / loading sequence from Planning when Clubbing Sheet is cancelled."""
	_clear_stamps_for_club(doc.name)


@frappe.whitelist()
def clear_planning_stamps_for_club(clubbing_sheet=None):
	"""Repair helper — clear stamps for a cancelled (or any) Clubbing Sheet name."""
	name = cstr(clubbing_sheet or "").strip()
	if not name:
		frappe.throw("clubbing_sheet required")
	n = _clear_stamps_for_club(name)
	return {"cleared": n, "clubbing_sheet": name}


def _clear_stamps_for_club(club_name):
	club_name = cstr(club_name).strip()
	if not club_name:
		return 0
	cleared = 0
	for dt in ("Planning Table", "Planning sheet Item"):
		if not frappe.db.has_column(dt, "custom_clubbing_sheet"):
			continue
		rows = frappe.db.sql(
			f"""
			select name from `tab{dt}`
			where custom_clubbing_sheet = %s
			""",
			club_name,
			as_dict=True,
		) or []
		for r in rows:
			vals = {"custom_clubbing_sheet": ""}
			if frappe.db.has_column(dt, "custom_loading_sequence"):
				vals["custom_loading_sequence"] = ""
			if frappe.db.has_column(dt, "custom_club_load_order"):
				vals["custom_club_load_order"] = 0
			frappe.db.set_value(dt, r.name, vals, update_modified=False)
			cleared += 1
	return cleared


def _resolve_pt_rows_for_item(item, club_name=""):
	"""Resolve exact Planning Table row(s). Never stamp whole SO / party."""
	ptr = cstr(item.get("planning_table_row") or item.get("custom_planning_table_row") or "").strip()
	if ptr and frappe.db.exists("Planning Table", ptr):
		parent = frappe.db.get_value("Planning Table", ptr, "parent")
		return [frappe._dict(pt_name=ptr, parent=parent)]

	# Fallback: unique match by SO/party + weight + rolls (+ gsm if present)
	so = cstr(item.get("sales_order") or "").strip()
	party = cstr(item.get("party_code") or "").strip()
	planning_sheet = cstr(item.get("planning_sheet") or item.get("custom_planning_sheet") or "").strip()
	weight = flt(item.get("weight_kgs"))
	rolls = flt(item.get("no_of_rolls"))
	gsm = item.get("gsm")
	quality = cstr(item.get("quality") or "").strip()
	color = cstr(item.get("color") or "").strip()

	sql = """
		select pt.name as pt_name, pt.parent
		from `tabPlanning Table` pt
		inner join `tabPlanning sheet` ps on ps.name = pt.parent
		where ifnull(pt.custom_movement_type, '') = 'Despatch'
		  and ifnull(ps.docstatus, 0) < 2
		  and abs(ifnull(pt.total_weight, 0) - %(wt)s) < 0.02
		  and abs(ifnull(pt.no_of_rolls, 0) - %(rolls)s) < 0.01
	"""
	args = {"wt": weight, "rolls": rolls}

	if planning_sheet:
		sql += " and ps.name = %(ps)s"
		args["ps"] = planning_sheet
	elif so:
		sql += " and ps.sales_order = %(so)s"
		args["so"] = so
	elif party:
		sql += " and ps.party_code = %(party)s"
		args["party"] = party
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

	if gsm is not None and cstr(gsm) != "" and frappe.db.has_column("Planning Table", "gsm"):
		sql += " and abs(ifnull(pt.gsm, 0) - %(gsm)s) < 0.01"
		args["gsm"] = flt(gsm)
	if quality and frappe.db.has_column("Planning Table", "quality"):
		sql += " and ifnull(pt.quality, '') = %(quality)s"
		args["quality"] = quality
	if color and frappe.db.has_column("Planning Table", "color"):
		sql += " and ifnull(pt.color, '') = %(color)s"
		args["color"] = color

	rows = frappe.db.sql(sql, args, as_dict=True) or []
	# Only accept exact unique match — never stamp multiple ambiguous rows
	if len(rows) == 1:
		return rows
	return []


def _stamp_pt(pt_name, club_name, seq, load_order, has_pt_club):
	if not has_pt_club:
		return
	vals = {"custom_clubbing_sheet": club_name}
	if frappe.db.has_column("Planning Table", "custom_loading_sequence"):
		vals["custom_loading_sequence"] = seq
	if frappe.db.has_column("Planning Table", "custom_club_load_order"):
		vals["custom_club_load_order"] = load_order
	frappe.db.set_value("Planning Table", pt_name, vals, update_modified=False)


def _stamp_psi_matching_pt(pt_name, parent, club_name, seq, load_order):
	"""Stamp PSI only when we can uniquely match the PT line — never all Despatch PSI."""
	if not parent or not frappe.db.has_column("Planning sheet Item", "custom_clubbing_sheet"):
		return

	fields = ["item_code", "total_weight", "no_of_rolls"]
	for f in ("gsm", "quality", "color"):
		if frappe.db.has_column("Planning Table", f):
			fields.append(f)
	pt = frappe.db.get_value("Planning Table", pt_name, fields, as_dict=True)
	if not pt:
		return

	sql = """
		select name from `tabPlanning sheet Item`
		where parent = %(parent)s
		  and ifnull(custom_movement_type, '') = 'Despatch'
		  and abs(ifnull(total_weight, 0) - %(wt)s) < 0.02
		  and abs(ifnull(no_of_rolls, 0) - %(rolls)s) < 0.01
	"""
	args = {
		"parent": parent,
		"wt": flt(pt.total_weight),
		"rolls": flt(pt.no_of_rolls),
	}
	if pt.item_code and frappe.db.has_column("Planning sheet Item", "item_code"):
		sql += " and ifnull(item_code, '') = %(ic)s"
		args["ic"] = cstr(pt.item_code)

	psi_rows = frappe.db.sql(sql, args, as_dict=True) or []
	if len(psi_rows) != 1:
		return

	pvals = {"custom_clubbing_sheet": club_name}
	if frappe.db.has_column("Planning sheet Item", "custom_loading_sequence"):
		pvals["custom_loading_sequence"] = seq
	if frappe.db.has_column("Planning sheet Item", "custom_club_load_order"):
		pvals["custom_club_load_order"] = load_order
	frappe.db.set_value("Planning sheet Item", psi_rows[0].name, pvals, update_modified=False)
