# -*- coding: utf-8 -*-
"""Install / migrate hooks for production_entry."""

import frappe


def after_migrate():
	_unblock_planning_sheet_doctype_desk_route()


def _unblock_planning_sheet_doctype_desk_route():
	"""
	If a Workspace document is named exactly like the DocType (``Planning Sheet``),
	Desk can resolve /planning-sheet/<docname> to the Workspace instead of the form — 404.

	See: frappe route conflict (Workspace vs DocType same name).
	Rename only the Workspace (data unchanged); DocType and all PLAN-* records stay as-is.
	"""
	if frappe.flags.in_test:
		return
	if not frappe.db.exists("DocType", "Planning Sheet"):
		return
	if not frappe.db.exists("Workspace", "Planning Sheet"):
		return
	new_name = "Planning Sheet Navigation"
	n = 1
	while frappe.db.exists("Workspace", new_name):
		new_name = f"Planning Sheet Navigation {n}"
		n += 1
	try:
		frappe.rename_doc(
			"Workspace",
			"Planning Sheet",
			new_name,
			merge=False,
			force=True,
		)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"production_entry: rename Workspace Planning Sheet — fix Desk route manually if Planning forms 404",
		)
