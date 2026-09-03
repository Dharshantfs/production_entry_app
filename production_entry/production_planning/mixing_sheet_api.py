# -*- coding: utf-8 -*-
"""Shift Mixing Sheet — load/save APIs (no PP, no WO/stock updates)."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime


API_MODULE = "production_entry.production_planning.mixing_sheet_api"


def _cstr(val) -> str:
	return (val or "").strip() if val is not None else ""


def _mixing_status_label(consumed_by, consumed_at) -> str:
	user = _cstr(consumed_by)
	label = user.split("@")[0] if user else "User"
	if hasattr(consumed_at, "strftime"):
		hhmm = consumed_at.strftime("%H:%M")
	else:
		s = _cstr(consumed_at)
		hhmm = s[11:16] if len(s) >= 16 else s
	if not hhmm:
		return label
	return f"{label} @ {hhmm}"


def _stamp_mixing_row_status(data: dict) -> dict:
	"""Write the grid Status text (e.g. Administrator @ 13:13) onto each consumed row in JSON."""
	if not isinstance(data, dict):
		return data
	for s in data.get("sets") or []:
		if not isinstance(s, dict):
			continue
		for row in s.get("rows") or []:
			if not isinstance(row, dict):
				continue
			if row.get("consumed"):
				row["status"] = _mixing_status_label(row.get("consumed_by"), row.get("consumed_at"))
	return data


def _empty_mixing_state() -> dict:
	return {"mixing_type": "", "sets": [{"materials": {}, "extras": [], "rows": []}], "completed": False}


def _parse_mixing_json(raw) -> dict:
	if not raw:
		return _empty_mixing_state()
	try:
		data = json.loads(raw) if isinstance(raw, str) else raw
	except Exception:
		return _empty_mixing_state()
	if not isinstance(data, dict):
		return _empty_mixing_state()
	sets = data.get("sets")
	if isinstance(sets, dict):
		# Legacy / corrupt saves stored a single set object instead of an array.
		data["sets"] = [sets]
	elif not isinstance(sets, list) or not sets:
		data["sets"] = [{"materials": {}, "extras": [], "rows": []}]
	else:
		normalized = []
		for s in sets:
			if isinstance(s, dict):
				normalized.append(s)
		data["sets"] = normalized or [{"materials": {}, "extras": [], "rows": []}]
	return data


def _normalize_shift(shift: str) -> str:
	s = _cstr(shift)
	if "night" in s.lower():
		return "Night Shift"
	if "day" in s.lower():
		return "Day Shift"
	return s


def _find_mixing_sheet(
	mixing_sheet_name=None,
	spr_name=None,
	gsm_shift_session=None,
	run_date=None,
	shift=None,
	custom_unit=None,
	order_code=None,
):
	"""One In Progress sheet per shift session + unit (or run_date + shift + unit)."""
	name = _cstr(mixing_sheet_name)
	if name and frappe.db.exists("Shift Mixing Sheet", name):
		return name

	session = _cstr(gsm_shift_session)
	unit = _cstr(custom_unit)
	shift_n = _normalize_shift(shift)
	rd = getdate(run_date) if run_date else None

	if session and unit:
		found = frappe.db.get_value(
			"Shift Mixing Sheet",
			{"gsm_shift_session": session, "custom_unit": unit, "status": "In Progress"},
			"name",
			order_by="modified desc",
		)
		if found:
			return found

	if rd and shift_n and unit:
		found = frappe.db.get_value(
			"Shift Mixing Sheet",
			{
				"run_date": rd,
				"shift": shift_n,
				"custom_unit": unit,
				"status": "In Progress",
			},
			"name",
			order_by="modified desc",
		)
		if found:
			return found

	return None


def _sheet_payload(doc) -> dict:
	data = _stamp_mixing_row_status(_parse_mixing_json(doc.mixing_sheet_data))
	return {
		"mixing_sheet_name": doc.name,
		"status": doc.status,
		"mixing_type": doc.mixing_type or data.get("mixing_type") or "",
		"existing_mixing_data": json.dumps(data),
		"run_date": str(doc.run_date or ""),
		"shift": doc.shift or "",
		"custom_unit": doc.custom_unit or "",
		"shaft_production_run": doc.shaft_production_run or "",
		"gsm_shift_session": doc.gsm_shift_session or "",
		"order_code": doc.order_code or "",
	}


@frappe.whitelist()
def get_mixing_sheet(
	mixing_sheet_name=None,
	spr_name=None,
	gsm_shift_session=None,
	run_date=None,
	shift=None,
	custom_unit=None,
	order_code=None,
):
	"""Load existing Shift Mixing Sheet or return empty template."""
	found = _find_mixing_sheet(
		mixing_sheet_name=mixing_sheet_name,
		spr_name=spr_name,
		gsm_shift_session=gsm_shift_session,
		run_date=run_date,
		shift=shift,
		custom_unit=custom_unit,
		order_code=order_code,
	)
	if found:
		return _sheet_payload(frappe.get_doc("Shift Mixing Sheet", found))

	unit = _cstr(custom_unit)

	return {
		"mixing_sheet_name": "",
		"status": "In Progress",
		"mixing_type": "",
		"existing_mixing_data": json.dumps(_empty_mixing_state()),
		"run_date": str(run_date or ""),
		"shift": _normalize_shift(shift),
		"custom_unit": unit,
		"shaft_production_run": "",
		"gsm_shift_session": _cstr(gsm_shift_session),
		"order_code": "",
	}


def _upsert_mixing_sheet(
	mixing_sheet_json,
	mixing_sheet_name=None,
	spr_name=None,
	gsm_shift_session=None,
	run_date=None,
	shift=None,
	custom_unit=None,
	order_code=None,
):
	data = _parse_mixing_json(mixing_sheet_json)
	data = _stamp_mixing_row_status(data)
	completed = cint(data.get("completed"))

	found = _find_mixing_sheet(
		mixing_sheet_name=mixing_sheet_name,
		spr_name=spr_name,
		gsm_shift_session=gsm_shift_session,
		run_date=run_date,
		shift=shift,
		custom_unit=custom_unit,
		order_code=order_code,
	)

	unit = _cstr(custom_unit)
	shift_n = _normalize_shift(shift)
	rd = getdate(run_date) if run_date else None
	session = _cstr(gsm_shift_session)

	if found:
		doc = frappe.get_doc("Shift Mixing Sheet", found)
	else:
		if not (rd and shift_n and unit):
			frappe.throw(_("Run Date, Shift, and Unit are required to create a mixing sheet."))
		doc = frappe.new_doc("Shift Mixing Sheet")
		doc.run_date = rd
		doc.shift = shift_n
		doc.custom_unit = unit

	if session:
		doc.gsm_shift_session = session
	if data.get("mixing_type"):
		doc.mixing_type = data.get("mixing_type")

	doc.mixing_sheet_data = json.dumps(data)
	doc.status = "Completed" if completed else "In Progress"
	if completed:
		doc.completed_by = frappe.session.user
		doc.completed_on = now_datetime()
	doc.save(ignore_permissions=True)
	try:
		_sync_shift_wise_mixing_list(doc, data)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Shift Wise Mixing List sync")
	frappe.db.commit()
	return _sheet_payload(doc)


@frappe.whitelist()
def save_shift_mixing_sheet(
	mixing_sheet_json,
	mixing_sheet_name=None,
	spr_name=None,
	gsm_shift_session=None,
	run_date=None,
	shift=None,
	custom_unit=None,
	order_code=None,
):
	return _upsert_mixing_sheet(
		mixing_sheet_json=mixing_sheet_json,
		mixing_sheet_name=mixing_sheet_name,
		spr_name=spr_name,
		gsm_shift_session=gsm_shift_session,
		run_date=run_date,
		shift=shift,
		custom_unit=custom_unit,
		order_code=order_code,
	)


@frappe.whitelist()
def record_mixing_consumption(
	set_index=0,
	row_index=0,
	state_json=None,
	mixing_sheet_name=None,
	spr_name=None,
	gsm_shift_session=None,
	run_date=None,
	shift=None,
	custom_unit=None,
):
	set_index = cint(set_index)
	row_index = cint(row_index)

	if state_json:
		data = _parse_mixing_json(state_json)
	else:
		found = _find_mixing_sheet(
			mixing_sheet_name=mixing_sheet_name,
			spr_name=spr_name,
			gsm_shift_session=gsm_shift_session,
			run_date=run_date,
			shift=shift,
			custom_unit=custom_unit,
		)
		if not found:
			frappe.throw(_("No mixing sheet found. Please save the sheet first."))
		raw = frappe.db.get_value("Shift Mixing Sheet", found, "mixing_sheet_data")
		data = _parse_mixing_json(raw)

	sets = data.get("sets") or []
	if set_index < len(sets) and row_index < len(sets[set_index].get("rows") or []):
		row = sets[set_index]["rows"][row_index]
		row["consumed"] = True
		row["consumed_by"] = frappe.session.user
		row["consumed_at"] = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
		row["status"] = _mixing_status_label(row.get("consumed_by"), row.get("consumed_at"))

	payload = _upsert_mixing_sheet(
		mixing_sheet_json=json.dumps(data),
		mixing_sheet_name=mixing_sheet_name,
		spr_name=spr_name,
		gsm_shift_session=gsm_shift_session,
		run_date=run_date,
		shift=shift,
		custom_unit=custom_unit,
	)
	payload["sets"] = data.get("sets")
	return payload


def _sync_shift_wise_mixing_list(sheet_doc, data: dict) -> None:
	"""Mirror mixing JSON into Shift Wise Mixing List child tables (one doc per date+shift+unit)."""
	if not frappe.db.exists("DocType", "Shift Wise Mixing List"):
		return
	unit = _cstr(sheet_doc.custom_unit)
	shift_n = _normalize_shift(sheet_doc.shift)
	rd = getdate(sheet_doc.run_date) if sheet_doc.run_date else None
	if not (rd and shift_n and unit):
		return

	found = frappe.db.get_value(
		"Shift Wise Mixing List",
		{"run_date": rd, "shift": shift_n, "custom_unit": unit},
		"name",
		order_by="modified desc",
	)
	if found:
		doc = frappe.get_doc("Shift Wise Mixing List", found)
	else:
		doc = frappe.new_doc("Shift Wise Mixing List")
		doc.run_date = rd
		doc.shift = shift_n
		doc.custom_unit = unit
	if sheet_doc.gsm_shift_session:
		doc.gsm_shift_session = sheet_doc.gsm_shift_session
	doc.shift_mixing_sheet = sheet_doc.name
	doc.material_sets = []
	doc.mixing_items = []
	for i, set_obj in enumerate(data.get("sets") or []):
		if not isinstance(set_obj, dict):
			continue
		materials = set_obj.get("materials") or {}
		names = set_obj.get("item_names") or {}
		if not (materials.get("PP") or materials.get("Ink")):
			continue
		set_no = i + 1
		doc.append(
			"material_sets",
			{
				"set_no": set_no,
				"polypropylene_item": _cstr(names.get("PP") or materials.get("PP")),
				"filler_item": _cstr(
					names.get("LD")
					or names.get("Filler")
					or materials.get("LD")
					or materials.get("Filler")
				),
				"modifier_item": _cstr(names.get("PPA") or materials.get("PPA")),
				"antistatic_item": _cstr(names.get("Antistatic") or materials.get("Antistatic")),
				"masterbatch_item": _cstr(names.get("Masterbatch") or materials.get("Masterbatch")),
			},
		)
		for ri, row in enumerate(set_obj.get("rows") or []):
			if not isinstance(row, dict):
				continue
			doc.append(
				"mixing_items",
				{
					"set_no": set_no,
					"row_no": ri + 1,
					"mixing_type": _cstr(row.get("mixing_type") or data.get("mixing_type")),
					"polypropylene": flt(row.get("pp_qty") or 0),
					"filler": flt(row.get("ld_qty") or row.get("filler_qty") or 0),
					"modifier": flt(row.get("ppa_qty") or 0),
					"antistatic": flt(row.get("anti_qty") or 0),
					"masterbatch": flt(row.get("mb_qty") or 0),
				},
			)
	doc.save(ignore_permissions=True)
