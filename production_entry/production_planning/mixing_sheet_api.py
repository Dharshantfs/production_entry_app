# -*- coding: utf-8 -*-
"""Shift Mixing Sheet — load/save APIs (no PP, no WO/stock updates)."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime


API_MODULE = "production_entry.production_planning.mixing_sheet_api"


def _cstr(val) -> str:
	return (val or "").strip() if val is not None else ""


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
	if not data.get("sets"):
		data["sets"] = [{"materials": {}, "extras": [], "rows": []}]
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
):
	name = _cstr(mixing_sheet_name)
	if name and frappe.db.exists("Shift Mixing Sheet", name):
		return name

	spr = _cstr(spr_name)
	if spr:
		found = frappe.db.get_value(
			"Shift Mixing Sheet",
			{"shaft_production_run": spr, "status": "In Progress"},
			"name",
			order_by="modified desc",
		)
		if found:
			return found
		found = frappe.db.get_value(
			"Shift Mixing Sheet",
			{"shaft_production_run": spr},
			"name",
			order_by="modified desc",
		)
		if found:
			return found

	session = _cstr(gsm_shift_session)
	unit = _cstr(custom_unit)
	shift_n = _normalize_shift(shift)
	rd = getdate(run_date) if run_date else None

	if session:
		filters = {"gsm_shift_session": session, "status": "In Progress"}
		if spr:
			filters["shaft_production_run"] = spr
		elif unit:
			filters["custom_unit"] = unit
		found = frappe.db.get_value("Shift Mixing Sheet", filters, "name", order_by="modified desc")
		if found:
			return found

	if rd and shift_n and unit:
		if spr:
			found = frappe.db.get_value(
				"Shift Mixing Sheet",
				{
					"run_date": rd,
					"shift": shift_n,
					"custom_unit": unit,
					"shaft_production_run": spr,
					"status": "In Progress",
				},
				"name",
				order_by="modified desc",
			)
			if found:
				return found
		else:
			rows = frappe.db.sql(
				"""
				SELECT name FROM `tabShift Mixing Sheet`
				WHERE run_date = %s AND shift = %s AND custom_unit = %s
				  AND status = 'In Progress'
				  AND (shaft_production_run IS NULL OR shaft_production_run = '')
				ORDER BY modified DESC LIMIT 1
				""",
				(rd, shift_n, unit),
			)
			if rows:
				return rows[0][0]

	return None


def _sheet_payload(doc) -> dict:
	data = _parse_mixing_json(doc.mixing_sheet_data)
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
):
	"""Load existing Shift Mixing Sheet or return empty template."""
	found = _find_mixing_sheet(
		mixing_sheet_name=mixing_sheet_name,
		spr_name=spr_name,
		gsm_shift_session=gsm_shift_session,
		run_date=run_date,
		shift=shift,
		custom_unit=custom_unit,
	)
	if found:
		doc = frappe.get_doc("Shift Mixing Sheet", found)
		return _sheet_payload(doc)

	unit = _cstr(custom_unit)
	if spr_name and not unit:
		unit = _cstr(frappe.db.get_value("Shaft Production Run", spr_name, "custom_unit"))

	return {
		"mixing_sheet_name": "",
		"status": "In Progress",
		"mixing_type": "",
		"existing_mixing_data": json.dumps(_empty_mixing_state()),
		"run_date": str(run_date or ""),
		"shift": _normalize_shift(shift),
		"custom_unit": unit,
		"shaft_production_run": _cstr(spr_name),
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
	completed = cint(data.get("completed"))

	found = _find_mixing_sheet(
		mixing_sheet_name=mixing_sheet_name,
		spr_name=spr_name,
		gsm_shift_session=gsm_shift_session,
		run_date=run_date,
		shift=shift,
		custom_unit=custom_unit,
	)

	unit = _cstr(custom_unit)
	shift_n = _normalize_shift(shift)
	rd = getdate(run_date) if run_date else None
	spr = _cstr(spr_name)
	session = _cstr(gsm_shift_session)
	oc = _cstr(order_code)

	if spr:
		if not unit:
			unit = _cstr(frappe.db.get_value("Shaft Production Run", spr, "custom_unit"))
		if not oc:
			oc = _cstr(frappe.db.get_value("Shaft Production Run", spr, "custom_order_code"))

	if found:
		doc = frappe.get_doc("Shift Mixing Sheet", found)
	else:
		if not (rd and shift_n and unit):
			frappe.throw(_("Run Date, Shift, and Unit are required to create a mixing sheet."))
		doc = frappe.new_doc("Shift Mixing Sheet")
		doc.run_date = rd
		doc.shift = shift_n
		doc.custom_unit = unit

	if spr:
		doc.shaft_production_run = spr
	if session:
		doc.gsm_shift_session = session
	if oc:
		doc.order_code = oc
	if data.get("mixing_type"):
		doc.mixing_type = data.get("mixing_type")

	doc.mixing_sheet_data = json.dumps(data)
	doc.status = "Completed" if completed else "In Progress"
	if completed:
		doc.completed_by = frappe.session.user
		doc.completed_on = now_datetime()
	doc.save(ignore_permissions=True)

	if spr and frappe.db.has_column("Shaft Production Run", "custom_shift_mixing_sheet"):
		frappe.db.set_value("Shaft Production Run", spr, "custom_shift_mixing_sheet", doc.name)

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
