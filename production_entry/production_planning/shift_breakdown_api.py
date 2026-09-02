# -*- coding: utf-8 -*-
"""Shift Breakdown — one document per date + shift + unit."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime


BREAKDOWN_REASONS = [
	"Mesh Change",
	"Mesh Clean",
	"Die Change",
	"Die Clean",
	"Breakdown - Partial",
	"Breakdown - Full",
	"EB Shutdown",
	"Machine Off",
	"Other",
]


def _cstr(val) -> str:
	return (val or "").strip() if val is not None else ""


def _normalize_shift(shift: str) -> str:
	s = _cstr(shift)
	if "night" in s.lower():
		return "Night Shift"
	if "day" in s.lower():
		return "Day Shift"
	return s


def _fmt_dt(val) -> str:
	if not val:
		return ""
	if hasattr(val, "strftime"):
		return val.strftime("%Y-%m-%d %H:%M:%S")
	return _cstr(val)


def _fmt_clock(val) -> str:
	s = _fmt_dt(val)
	if len(s) >= 16:
		return s[11:16]
	return s


def _row_payload(row) -> dict:
	stop = getattr(row, "stop_time", None)
	on = getattr(row, "on_time", None)
	return {
		"name": row.name,
		"stop_time": _fmt_dt(stop),
		"on_time": _fmt_dt(on),
		"stop_clock": _fmt_clock(stop),
		"on_clock": _fmt_clock(on),
		"reason": _cstr(getattr(row, "reason", None)),
		"remarks": _cstr(getattr(row, "remarks", None)),
		"open": not bool(on),
	}


def _doc_payload(doc, carried_from=None) -> dict:
	rows = [_row_payload(r) for r in (doc.breakdowns or [])]
	open_row = next((r for r in reversed(rows) if r.get("open")), None)
	return {
		"name": doc.name,
		"run_date": str(doc.run_date or ""),
		"shift": doc.shift or "",
		"custom_unit": doc.custom_unit or "",
		"gsm_shift_session": doc.gsm_shift_session or "",
		"open_row": open_row,
		"rows": rows,
		"reasons": BREAKDOWN_REASONS,
		"carried_from": carried_from,
	}


def _empty_payload(run_date=None, shift=None, custom_unit=None, gsm_shift_session=None) -> dict:
	return {
		"name": "",
		"run_date": str(run_date or ""),
		"shift": _normalize_shift(shift),
		"custom_unit": _cstr(custom_unit),
		"gsm_shift_session": _cstr(gsm_shift_session),
		"open_row": None,
		"rows": [],
		"reasons": BREAKDOWN_REASONS,
		"carried_from": None,
	}


def _find_open_breakdown_for_unit(unit: str) -> dict | None:
	"""Latest unclosed stop for this unit, any date/shift."""
	unit = _cstr(unit)
	if not unit:
		return None
	rows = frappe.db.sql(
		"""
		SELECT r.parent AS parent, r.name AS row_name
		FROM `tabShift Breakdown Row` r
		INNER JOIN `tabShift Breakdown` p ON p.name = r.parent
		WHERE p.custom_unit = %s
		  AND (r.on_time IS NULL OR CAST(r.on_time AS CHAR) = '')
		ORDER BY r.stop_time DESC
		LIMIT 1
		""",
		(unit,),
		as_dict=True,
	)
	return rows[0] if rows else None


def _carried_from_meta(open_doc, run_date=None, shift=None) -> dict | None:
	if not open_doc:
		return None
	cur_date = str(getdate(run_date) if run_date else "")
	cur_shift = _normalize_shift(shift)
	open_date = str(open_doc.run_date or "")
	open_shift = _normalize_shift(open_doc.shift)
	if open_date == cur_date and open_shift == cur_shift:
		return None
	return {
		"name": open_doc.name,
		"run_date": open_date,
		"shift": open_shift,
		"custom_unit": open_doc.custom_unit or "",
	}


def _apply_open_carry(payload: dict, unit: str, run_date=None, shift=None) -> dict:
	open_info = _find_open_breakdown_for_unit(unit)
	if not open_info:
		payload["carried_from"] = payload.get("carried_from")
		return payload
	open_doc = frappe.get_doc("Shift Breakdown", open_info["parent"])
	open_row = next(
		(r for r in reversed(open_doc.breakdowns or []) if not getattr(r, "on_time", None)),
		None,
	)
	if not open_row:
		return payload
	row = _row_payload(open_row)
	payload["open_row"] = row
	payload["name"] = open_doc.name
	carried = _carried_from_meta(open_doc, run_date=run_date, shift=shift)
	payload["carried_from"] = carried
	if carried and not any(r.get("name") == row.get("name") for r in (payload.get("rows") or [])):
		payload["rows"] = [row] + list(payload.get("rows") or [])
	return payload


def _find_breakdown(run_date=None, shift=None, custom_unit=None, gsm_shift_session=None, name=None):
	name = _cstr(name)
	if name and frappe.db.exists("Shift Breakdown", name):
		return name
	session = _cstr(gsm_shift_session)
	unit = _cstr(custom_unit)
	shift_n = _normalize_shift(shift)
	rd = getdate(run_date) if run_date else None
	if session and unit:
		found = frappe.db.get_value(
			"Shift Breakdown",
			{"gsm_shift_session": session, "custom_unit": unit},
			"name",
			order_by="modified desc",
		)
		if found:
			return found
	if rd and shift_n and unit:
		found = frappe.db.get_value(
			"Shift Breakdown",
			{"run_date": rd, "shift": shift_n, "custom_unit": unit},
			"name",
			order_by="modified desc",
		)
		if found:
			return found
	return None


def _get_or_create(run_date=None, shift=None, custom_unit=None, gsm_shift_session=None, name=None):
	found = _find_breakdown(
		run_date=run_date,
		shift=shift,
		custom_unit=custom_unit,
		gsm_shift_session=gsm_shift_session,
		name=name,
	)
	if found:
		doc = frappe.get_doc("Shift Breakdown", found)
	else:
		unit = _cstr(custom_unit)
		shift_n = _normalize_shift(shift)
		rd = getdate(run_date) if run_date else None
		if not (rd and shift_n and unit):
			frappe.throw(_("Date, Shift, and Unit are required to record a breakdown."))
		doc = frappe.new_doc("Shift Breakdown")
		doc.run_date = rd
		doc.shift = shift_n
		doc.custom_unit = unit
	session = _cstr(gsm_shift_session)
	if session:
		doc.gsm_shift_session = session
	return doc


@frappe.whitelist()
def get_shift_breakdown(
	run_date=None,
	shift=None,
	custom_unit=None,
	gsm_shift_session=None,
	breakdown_name=None,
):
	found = _find_breakdown(
		run_date=run_date,
		shift=shift,
		custom_unit=custom_unit,
		gsm_shift_session=gsm_shift_session,
		name=breakdown_name,
	)
	if found:
		return _apply_open_carry(
			_doc_payload(frappe.get_doc("Shift Breakdown", found)),
			_cstr(custom_unit),
			run_date=run_date,
			shift=shift,
		)
	empty = _empty_payload(run_date, shift, custom_unit, gsm_shift_session)
	return _apply_open_carry(empty, _cstr(custom_unit), run_date=run_date, shift=shift)


@frappe.whitelist()
def record_machine_stop(
	run_date=None,
	shift=None,
	custom_unit=None,
	gsm_shift_session=None,
	reason=None,
	remarks=None,
	breakdown_name=None,
):
	reason = _cstr(reason)
	if reason not in BREAKDOWN_REASONS:
		frappe.throw(_("Select a valid breakdown reason."))
	unit = _cstr(custom_unit)
	open_info = _find_open_breakdown_for_unit(unit)
	if open_info:
		open_doc = frappe.get_doc("Shift Breakdown", open_info["parent"])
		frappe.throw(
			_("Machine is already stopped since {0} {1}. Record Machine On before starting another breakdown.").format(
				open_doc.run_date, open_doc.shift
			)
		)
	doc = _get_or_create(
		run_date=run_date,
		shift=shift,
		custom_unit=custom_unit,
		gsm_shift_session=gsm_shift_session,
		name=None,
	)
	open_row = next((r for r in reversed(doc.breakdowns or []) if not r.on_time), None)
	if open_row:
		frappe.throw(_("Machine is already stopped. Record Machine On before starting another breakdown."))
	now = now_datetime()
	doc.append(
		"breakdowns",
		{"stop_time": now, "on_time": None, "reason": reason, "remarks": _cstr(remarks)},
	)
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	payload = _doc_payload(doc)
	payload["recorded_stop"] = now.strftime("%H:%M")
	return payload


@frappe.whitelist()
def record_machine_on(
	run_date=None,
	shift=None,
	custom_unit=None,
	gsm_shift_session=None,
	breakdown_name=None,
):
	unit = _cstr(custom_unit)
	open_info = _find_open_breakdown_for_unit(unit)
	found = None
	if open_info:
		found = open_info["parent"]
	if not found:
		found = _find_breakdown(
			run_date=run_date,
			shift=shift,
			custom_unit=custom_unit,
			gsm_shift_session=gsm_shift_session,
			name=breakdown_name,
		)
	if not found:
		frappe.throw(_("No open breakdown found. Record Machine Stop first."))
	doc = frappe.get_doc("Shift Breakdown", found)
	open_row = next((r for r in reversed(doc.breakdowns or []) if not r.on_time), None)
	if not open_row:
		frappe.throw(_("No open breakdown found. Record Machine Stop first."))
	now = now_datetime()
	open_row.on_time = now
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	payload = _apply_open_carry(
		_doc_payload(doc),
		unit,
		run_date=run_date,
		shift=shift,
	)
	payload["recorded_on"] = now.strftime("%H:%M")
	return payload
