# -*- coding: utf-8 -*-
"""Recreate Production Board Access child DocTypes only when missing.

Earlier migrate patches used reload_doc(force=True) and could overwrite
manually created child tables on the site. This patch is safe: it only
imports when the DocType row does not exist.
"""
import os

import frappe

_CHILD = (
	("Production Board Access Unit", "production_board_access_unit"),
	("Production Board Access Board", "production_board_access_board"),
)


def execute():
	from frappe.modules.import_file import import_file_by_path

	app_path = frappe.get_app_path("production_entry")
	base = os.path.join(app_path, "production_planning", "doctype")
	created = []

	for dt_name, folder in _CHILD:
		if frappe.db.exists("DocType", dt_name):
			continue
		path = os.path.join(base, folder, f"{folder}.json")
		if os.path.exists(path):
			import_file_by_path(path, force=True, ignore_version=True)
			created.append(dt_name)
			continue
		try:
			frappe.reload_doc("production_planning", "doctype", folder)
			created.append(dt_name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"repair_production_board_access_child_doctypes: {dt_name}")

	if created:
		frappe.log_error(
			f"Recreated missing child DocTypes: {', '.join(created)}",
			"repair_production_board_access_child_doctypes",
		)

	frappe.db.commit()
	frappe.clear_cache()
