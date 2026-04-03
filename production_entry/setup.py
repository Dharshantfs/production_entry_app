# -*- coding: utf-8 -*-
"""Migrate hooks for production_entry."""

import frappe


def after_migrate():
	_rename_planning_sheet_workspace_if_it_hijacks_doctype_route()


def _rename_planning_sheet_workspace_if_it_hijacks_doctype_route():
	"""
	A Workspace named exactly like the DocType steals the same Desk route as the form
	(Frappe Desk: workspace vs doctype route). Users see 404 / not found though data exists.
	Rename only the Workspace document; Planning Sheet data is untouched.
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
		n += 1
		new_name = f"Planning Sheet Navigation {n}"
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
			"production_entry: rename Workspace Planning Sheet (route clash with DocType)",
		)
