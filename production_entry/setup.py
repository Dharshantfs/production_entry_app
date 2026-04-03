# -*- coding: utf-8 -*-
"""Install / migrate hooks for production_entry."""

import frappe

from production_entry.production_planning.planning_doctypes import (
	LEGACY_PLANNING_SHEET,
	PLANNING_SHEET,
)


def after_install():
	"""Ensure app JSON (DocTypes, workspaces) is loaded on first install."""
	if frappe.flags.in_test:
		return
	_sync_app_if_planning_missing()


def after_migrate():
	_sync_app_if_planning_missing()
	_fix_planning_sheet_child_parenttype()
	_rename_workspace_that_hijacks_planning_sheet_route()


def _sync_app_if_planning_missing():
	"""
	If ``Planning sheet`` is not in ``tabDocType``, the app JSON never reached the site
	(packaging / failed migrate / app not fully installed). Re-sync — does not delete table data.
	"""
	if frappe.flags.in_test:
		return
	if frappe.db.exists("DocType", PLANNING_SHEET):
		return
	if "production_entry" not in frappe.get_installed_apps():
		return
	try:
		from frappe.model.sync import sync_for

		sync_for("production_entry")
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"production_entry: sync_for failed while Planning sheet DocType was missing",
		)


def _fix_planning_sheet_child_parenttype():
	"""Legacy rows used parenttype ``Planning Sheet``; DB DocType is ``Planning sheet``."""
	if not frappe.db.exists("DocType", PLANNING_SHEET):
		return
	table = "`tabPlanning sheet Item`"
	try:
		frappe.db.sql(
			f"UPDATE {table} SET parenttype = %s WHERE IFNULL(parenttype, '') = %s",
			(PLANNING_SHEET, LEGACY_PLANNING_SHEET),
		)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"production_entry: fix Planning sheet Item parenttype",
		)


def _rename_workspace_that_hijacks_planning_sheet_route():
	"""Workspace with same name as DocType breaks desk form/list routes."""
	if frappe.flags.in_test:
		return
	if not frappe.db.exists("DocType", PLANNING_SHEET):
		return
	for ws in (PLANNING_SHEET, LEGACY_PLANNING_SHEET):
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
