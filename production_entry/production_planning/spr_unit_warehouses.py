# -*- coding: utf-8 -*-
"""Resolve manufacturing warehouses (RM / WIP / FG) for an SPR unit via Workstation → Plant Floor."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from production_entry.production_planning.planning_doctypes import (
	normalize_planning_unit_for_select,
	resolve_mix_roll_company_and_fg_warehouse,
	resolve_planning_workstation_name,
)


def _cstr(v) -> str:
	return "" if v is None else str(v).strip()


def _extract_warehouse_suffix(warehouse_name: str) -> str:
	"""Return trailing unit token from names like 'Finished Goods Warehouse - VTP'."""
	name = _cstr(warehouse_name)
	if " - " in name:
		return name.rsplit(" - ", 1)[-1].strip()
	return ""


def _plant_floor_from_workstation(ws_name: str) -> str:
	ws_name = _cstr(ws_name)
	if not ws_name or not frappe.db.exists("Workstation", ws_name):
		return ""
	ws_meta = frappe.get_meta("Workstation")
	if ws_meta.has_field("plant_floor"):
		pf = _cstr(frappe.db.get_value("Workstation", ws_name, "plant_floor"))
		if pf and frappe.db.exists("Plant Floor", pf):
			return pf
	if frappe.db.exists("DocType", "Plant Floor Workstation"):
		pf = frappe.db.get_value("Plant Floor Workstation", {"workstation": ws_name}, "parent")
		if pf and frappe.db.exists("Plant Floor", pf):
			return pf
	return ""


def _plant_floor_company_and_fg(pf_name: str) -> tuple[str, str]:
	pf_name = _cstr(pf_name)
	if not pf_name:
		return "", ""
	pf_meta = frappe.get_meta("Plant Floor")
	fields = ["name"]
	if pf_meta.has_field("company"):
		fields.append("company")
	if pf_meta.has_field("warehouse"):
		fields.append("warehouse")
	row = frappe.db.get_value("Plant Floor", pf_name, fields, as_dict=True) or {}
	company = _cstr(row.get("company"))
	fg_wh = _cstr(row.get("warehouse"))
	if fg_wh and not frappe.db.exists("Warehouse", fg_wh):
		fg_wh = ""
	if company and not frappe.db.exists("Company", company):
		company = ""
	return company, fg_wh


def _find_leaf_warehouse(company: str, name_patterns: tuple[str, ...], suffix: str = "", exclude: str = "") -> str:
	company = _cstr(company)
	suffix = _cstr(suffix)
	exclude = _cstr(exclude)
	if not company:
		return ""
	for pattern in name_patterns:
		core = pattern.strip("%")
		if suffix:
			like_val = f"%{core}%{suffix}%"
			wh = frappe.db.get_value(
				"Warehouse",
				{"company": company, "is_group": 0, "name": ["like", like_val]},
				"name",
				order_by="modified desc",
			)
		else:
			wh = frappe.db.get_value(
				"Warehouse",
				{"company": company, "is_group": 0, "name": ["like", pattern]},
				"name",
				order_by="modified desc",
			)
		wh = _cstr(wh)
		if wh and wh != exclude and "work in progress" not in wh.lower():
			return wh
	# Broader search with suffix only on name ending
	if suffix:
		for pattern in name_patterns:
			core = pattern.strip("%").lower()
			rows = frappe.db.sql(
				"""
				SELECT name
				FROM `tabWarehouse`
				WHERE company = %s
				  AND IFNULL(is_group, 0) = 0
				  AND LOWER(name) LIKE %s
				  AND LOWER(name) LIKE %s
				  AND IFNULL(name, '') != %s
				ORDER BY modified DESC
				LIMIT 5
				""",
				(company, f"%{core}%", f"%{suffix.lower()}%", exclude),
				as_dict=True,
			)
			for row in rows or []:
				wh = _cstr(row.get("name"))
				if wh and wh != exclude:
					return wh
	return ""


def _company_rm_warehouse(company: str, wip_wh: str = "", suffix: str = "") -> str:
	wh = _find_leaf_warehouse(
		company,
		("%Raw Material%", "%Raw Materials%", "%RM Warehouse%"),
		suffix=suffix,
		exclude=wip_wh,
	)
	if wh:
		return wh
	# Generic company fallback (mirrors _spr_company_rm_warehouse)
	for pattern in ("%Raw Material%", "%Raw Materials%", "%RM Warehouse%", "%Stores%", "%Material%"):
		for is_group in (0, 1):
			cand = frappe.db.get_value(
				"Warehouse",
				{"company": company, "name": ["like", pattern], "is_group": is_group},
				"name",
				order_by="modified desc",
			)
			cand = _cstr(cand)
			if cand and cand != wip_wh and "work in progress" not in cand.lower():
				if is_group:
					leaf = frappe.db.get_value(
						"Warehouse",
						{"company": company, "parent_warehouse": cand, "is_group": 0},
						"name",
						order_by="modified desc",
					)
					leaf = _cstr(leaf)
					if leaf and leaf != wip_wh:
						return leaf
				else:
					return cand
	return ""


def _company_wip_warehouse(company: str, suffix: str = "") -> str:
	wh = _find_leaf_warehouse(
		company,
		("%Work In Progress%", "%WIP%"),
		suffix=suffix,
	)
	if wh:
		return wh
	for pattern in ("%Work In Progress%", "%WIP%"):
		wh = frappe.db.get_value(
			"Warehouse",
			{"company": company, "is_group": 0, "name": ["like", pattern]},
			"name",
			order_by="modified desc",
		)
		wh = _cstr(wh)
		if wh:
			return wh
	try:
		default_wip = _cstr(frappe.db.get_single_value("Stock Settings", "default_wip_warehouse"))
		if default_wip and frappe.db.get_value("Warehouse", default_wip, "company") == company:
			return default_wip
	except Exception:
		pass
	return ""


def resolve_spr_unit_manufacturing_warehouses(unit: str) -> dict:
	"""
	Return manufacturing warehouses for an SPR unit.

	Keys: company, source_warehouse, wip_warehouse, fg_warehouse, plant_floor, workstation.
	"""
	unit_norm = normalize_planning_unit_for_select(_cstr(unit))
	ws_name = resolve_planning_workstation_name(unit_norm or unit)
	pf_name = _plant_floor_from_workstation(ws_name) if ws_name else ""
	company, fg_wh = _plant_floor_company_and_fg(pf_name) if pf_name else ("", "")

	if not company or not fg_wh:
		mix_co, mix_fg = resolve_mix_roll_company_and_fg_warehouse(unit_norm or unit)
		if not company:
			company = mix_co
		if not fg_wh:
			fg_wh = mix_fg

	if not company:
		company = _cstr(
			frappe.defaults.get_user_default("Company")
			or frappe.db.get_single_value("Global Defaults", "default_company")
		)

	suffix = _extract_warehouse_suffix(fg_wh)
	if not suffix and pf_name:
		# Try parent group warehouse name for suffix (e.g. All Warehouses - VTP)
		parent = frappe.db.get_value("Warehouse", fg_wh, "parent_warehouse") if fg_wh else ""
		suffix = _extract_warehouse_suffix(parent)

	wip_wh = _company_wip_warehouse(company, suffix=suffix)
	source_wh = _company_rm_warehouse(company, wip_wh=wip_wh, suffix=suffix)

	if not fg_wh:
		fg_wh = frappe.db.get_value(
			"Warehouse",
			{"company": company, "is_group": 0, "name": ["like", "%Finished%"]},
			"name",
			order_by="modified desc",
		)
		fg_wh = _cstr(fg_wh)

	missing = []
	if not company:
		missing.append(_("Company"))
	if not source_wh:
		missing.append(_("Raw Materials warehouse"))
	if not wip_wh:
		missing.append(_("Work In Progress warehouse"))
	if not fg_wh:
		missing.append(_("Finished Goods warehouse"))

	if missing:
		hint = ws_name or unit_norm or unit or _("unit")
		frappe.throw(
			_(
				"Could not resolve {0} for {1}. Configure Plant Floor (company + FG warehouse) "
				"on Workstation {2} and matching RM/WIP warehouses in the warehouse tree."
			).format(", ".join(missing), hint, ws_name or "—"),
			title=_("Warehouse configuration missing"),
		)

	return {
		"company": company,
		"source_warehouse": source_wh,
		"wip_warehouse": wip_wh,
		"fg_warehouse": fg_wh,
		"plant_floor": pf_name,
		"workstation": ws_name,
	}
