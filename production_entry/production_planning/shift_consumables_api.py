# -*- coding: utf-8 -*-
"""Shift Wise Consumable List — one document per date + shift + unit.

Replaces the old Shift Consumables DocType for GSM. Method names stay stable
so the GSM dialog keeps calling get/save_shift_consumables.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate

DOCTYPE = "Shift Wise Consumable List"


def _cstr(val) -> str:
	return (val or "").strip() if val is not None else ""


def _normalize_shift(shift: str) -> str:
	s = _cstr(shift)
	if "night" in s.lower():
		return "Night Shift"
	if "day" in s.lower():
		return "Day Shift"
	return s


def _parse_rows(rows) -> list:
	if isinstance(rows, str):
		try:
			rows = json.loads(rows)
		except Exception:
			rows = []
	return rows if isinstance(rows, list) else []


def _item_details(item_code: str) -> dict:
	item_code = _cstr(item_code)
	if not item_code or not frappe.db.exists("Item", item_code):
		return {"item_code": item_code, "item_name": "", "uom": "", "item_group": ""}
	row = frappe.db.get_value("Item", item_code, ["item_name", "stock_uom", "item_group"], as_dict=True) or {}
	return {
		"item_code": item_code,
		"item_name": _cstr(row.get("item_name")),
		"uom": _cstr(row.get("stock_uom")),
		"item_group": _cstr(row.get("item_group")),
	}


def _excluded_product_item_groups() -> list:
	"""Products / Finished Goods groups and their descendants — hidden from consumable pickers."""
	roots = []
	for name in ("Products", "Product", "Finished Goods", "Finished Good"):
		if frappe.db.exists("Item Group", name):
			roots.append(name)
	if not roots:
		return ["Products", "Finished Goods"]
	groups = set(roots)
	try:
		from frappe.utils.nestedset import get_descendants_of

		for root in roots:
			for child in get_descendants_of("Item Group", root, ignore_permissions=True) or []:
				if child:
					groups.add(child)
	except Exception:
		pass
	return sorted(groups)


def _is_allowed_consumable_item(item_code: str) -> bool:
	item_code = _cstr(item_code)
	if not item_code:
		return False
	group = _cstr(frappe.db.get_value("Item", item_code, "item_group"))
	if not group:
		return True
	return group not in set(_excluded_product_item_groups())


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def consumable_item_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link search: all item groups except Products / Finished Goods (and children)."""
	excluded = _excluded_product_item_groups()
	txt = _cstr(txt)
	return frappe.db.sql(
		"""
		SELECT name, item_name, item_group
		FROM `tabItem`
		WHERE disabled = 0
		  AND IFNULL(item_group, '') NOT IN %(excluded)s
		  AND (
			name LIKE %(txt)s
			OR item_name LIKE %(txt)s
		  )
		ORDER BY
			CASE WHEN name LIKE %(exact)s THEN 0 ELSE 1 END,
			name
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"excluded": excluded or [""],
			"txt": f"%{txt}%",
			"exact": f"{txt}%",
			"start": start,
			"page_len": page_len,
		},
	)


# Back-compat alias used by older client bundles
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def raw_material_item_query(doctype, txt, searchfield, start, page_len, filters):
	return consumable_item_query(doctype, txt, searchfield, start, page_len, filters)


def _row_payload(row) -> dict:
	return {
		"name": _cstr(getattr(row, "name", None)),
		"item_code": _cstr(getattr(row, "item_code", None)),
		"item_name": _cstr(getattr(row, "item_name", None)),
		"quantity": flt(getattr(row, "quantity", None) or 0),
		"uom": _cstr(getattr(row, "uom", None)),
	}


def _doc_payload(doc) -> dict:
	return {
		"name": doc.name,
		"run_date": str(doc.run_date or ""),
		"shift": doc.shift or "",
		"custom_unit": doc.custom_unit or "",
		"gsm_shift_session": doc.gsm_shift_session or "",
		"rows": [_row_payload(r) for r in (doc.items or [])],
	}


def _doctype_ready() -> bool:
	return bool(frappe.db.exists("DocType", DOCTYPE))


def _find_doc(run_date=None, shift=None, custom_unit=None, gsm_shift_session=None, name=None):
	if not _doctype_ready():
		return None
	name = _cstr(name)
	if name and frappe.db.exists(DOCTYPE, name):
		return name
	session = _cstr(gsm_shift_session)
	unit = _cstr(custom_unit)
	shift_n = _normalize_shift(shift)
	rd = getdate(run_date) if run_date else None
	if session and unit:
		found = frappe.db.get_value(
			DOCTYPE,
			{"gsm_shift_session": session, "custom_unit": unit},
			"name",
			order_by="modified desc",
		)
		if found:
			return found
	if rd and shift_n and unit:
		found = frappe.db.get_value(
			DOCTYPE,
			{"run_date": rd, "shift": shift_n, "custom_unit": unit},
			"name",
			order_by="modified desc",
		)
		if found:
			return found
	return None


def _get_or_create(run_date=None, shift=None, custom_unit=None, gsm_shift_session=None, name=None):
	if not _doctype_ready():
		frappe.throw(_("Shift Wise Consumable List is not installed. Run bench migrate."))
	found = _find_doc(
		run_date=run_date,
		shift=shift,
		custom_unit=custom_unit,
		gsm_shift_session=gsm_shift_session,
		name=name,
	)
	if found:
		doc = frappe.get_doc(DOCTYPE, found)
	else:
		unit = _cstr(custom_unit)
		shift_n = _normalize_shift(shift)
		rd = getdate(run_date) if run_date else None
		if not (rd and shift_n and unit):
			frappe.throw(_("Date, Shift, and Unit are required to save shift consumables."))
		doc = frappe.new_doc(DOCTYPE)
		doc.run_date = rd
		doc.shift = shift_n
		doc.custom_unit = unit
	session = _cstr(gsm_shift_session)
	if session:
		doc.gsm_shift_session = session
	return doc


@frappe.whitelist()
def get_shift_consumables(
	run_date=None,
	shift=None,
	custom_unit=None,
	gsm_shift_session=None,
	doc_name=None,
):
	found = _find_doc(
		run_date=run_date,
		shift=shift,
		custom_unit=custom_unit,
		gsm_shift_session=gsm_shift_session,
		name=doc_name,
	)
	if found:
		return _doc_payload(frappe.get_doc(DOCTYPE, found))
	return {
		"name": "",
		"run_date": str(run_date or ""),
		"shift": _normalize_shift(shift),
		"custom_unit": _cstr(custom_unit),
		"gsm_shift_session": _cstr(gsm_shift_session),
		"rows": [],
	}


@frappe.whitelist()
def get_consumable_item_details(item_code=None):
	item_code = _cstr(item_code)
	if not item_code:
		frappe.throw(_("Select an item code."))
	return _item_details(item_code)


@frappe.whitelist()
def save_shift_consumables(
	run_date=None,
	shift=None,
	custom_unit=None,
	gsm_shift_session=None,
	doc_name=None,
	rows=None,
):
	rows = _parse_rows(rows)
	doc = _get_or_create(
		run_date=run_date,
		shift=shift,
		custom_unit=custom_unit,
		gsm_shift_session=gsm_shift_session,
		name=doc_name,
	)
	doc.items = []
	for raw in rows:
		if not isinstance(raw, dict):
			continue
		item_code = _cstr(raw.get("item_code"))
		if not item_code:
			continue
		if not _is_allowed_consumable_item(item_code):
			frappe.throw(
				_("Item {0} is in Products / Finished Goods. Choose another item group.").format(item_code)
			)
		details = _item_details(item_code)
		doc.append(
			"items",
			{
				"item_code": item_code,
				"item_name": details.get("item_name") or _cstr(raw.get("item_name")),
				"quantity": flt(raw.get("quantity") or 0),
				"uom": details.get("uom") or _cstr(raw.get("uom")),
			},
		)
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return _doc_payload(doc)
