# Copyright (c) 2026, production_entry contributors
"""Resolve Desk route clash between Workspace and DocType named alike (Frappe #37900).

If a Workspace document is named exactly ``Planning Sheet``, it steals the same route as
the Planning Sheet DocType. Opening ``/desk/planning_sheet/PLAN-...`` then fails with 404.
Rename that workspace to a distinct name so form URLs work again.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Planning Sheet"):
		return
	if not frappe.db.exists("Workspace", "Planning Sheet"):
		return
	try:
		frappe.rename_doc(
			"Workspace",
			"Planning Sheet",
			"Production Planning Hub",
			merge=False,
			force=True,
		)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"rename_planning_sheet_workspace_conflict: rename failed (fix manually if needed)",
		)
		raise
