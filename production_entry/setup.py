# -*- coding: utf-8 -*-
"""Migrate hooks for production_entry."""

import frappe

# Live DB / legacy sites use this exact DocType name (table `tabPlanning sheet`).
PLANNING_SHEET_DOCTYPE = "Planning sheet"


def _fix_planning_sheet_child_parenttype():
	"""Old deploys used DocType name ``Planning Sheet``; live DB uses ``Planning sheet``. Align child rows (no deletes)."""
	if not frappe.db.exists("DocType", PLANNING_SHEET_DOCTYPE):
		return
	table = "`tabPlanning sheet Item`"
	try:
		frappe.db.sql(
			f"UPDATE {table} SET parenttype = %s WHERE IFNULL(parenttype, '') = %s",
			(PLANNING_SHEET_DOCTYPE, "Planning Sheet"),
		)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"production_entry: fix Planning sheet Item parenttype",
		)


def after_migrate():
	_fix_planning_sheet_child_parenttype()
	_rename_workspace_that_hijacks_planning_sheet_route()


def _rename_workspace_that_hijacks_planning_sheet_route():
	"""
	A Workspace whose name equals the Planning sheet DocType can steal the same Desk route
	as the form (404 / not found while rows exist in `tabPlanning sheet`).
	Rename only Workspace documents; data tables are untouched.
	"""
	if frappe.flags.in_test:
		return
	if not frappe.db.exists("DocType", PLANNING_SHEET_DOCTYPE):
		return
	for ws in ("Planning sheet", "Planning Sheet"):
		if not frappe.db.exists("Workspace", ws):
			continue
		new_name = f"{ws} Navigation"
		n = 1
		while frappe.db.exists("Workspace", new_name):
			n += 1
			new_name = f"{ws} Navigation {n}"
		try:
			frappe.rename_doc("Workspace", ws, new_name, merge=False, force=True)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"production_entry: rename Workspace that clashes with Planning sheet DocType route",
			)
