# -*- coding: utf-8 -*-
"""
Install / migrate hooks for production_entry.

Data safety (existing planning / board / chart data)
------------------------------------------------------
* Migrate path is **additive**: Frappe sync adds or updates DocType metadata and missing DB
  columns/tables. It does **not** truncate ``tabPlanning sheet``, child tables, or board state.
* :func:`_fix_planning_sheet_child_parenttype` only **UPDATE**s ``parenttype`` on legacy child rows;
  it does not delete rows.
* ``patches.txt`` runs only ``repair_istable_schema_columns``, which **ADD**s ``parent``/``idx``
  columns to child tables when missing — no mass deletes.
* Scheduler API code may contain ``DELETE`` statements for **explicit user/admin flows** (split,
  merge cleanup). Those run only when that API is called, **not** during install/migrate.
* Global Defaults keys for saved board/chart plans keep the ``production_scheduler_*`` names so
  existing persisted UI state continues to resolve.

If **both** ``production_scheduler`` and ``production_entry`` stay on the same site, document
hooks can fire twice — use one app only after validation (see :func:`_warn_if_duplicate_scheduler_app`).
"""

import json

import frappe

from production_entry.production_planning.planning_doctypes import (
	LEGACY_PLANNING_SHEET,
	PLANNING_SHEET,
)

WORKSPACE_PRODUCTION_ENTRY_DESK = "Production Entry Desk"


def after_install():
	"""Ensure app JSON (DocTypes, workspaces) is loaded on first install."""
	if frappe.flags.in_test:
		return
	_sync_app_if_planning_missing()
	_sync_production_queue_custom_block()
	_ensure_workspace_shows_production_queue()


def after_migrate():
	_sync_app_if_planning_missing()
	_fix_planning_sheet_child_parenttype()
	_rename_workspace_that_hijacks_planning_sheet_route()
	_sync_production_queue_custom_block()
	_ensure_workspace_shows_production_queue()
	_warn_if_duplicate_scheduler_app()


def _warn_if_duplicate_scheduler_app():
	"""
	Log once per migrate if two apps both register the same document hooks — can duplicate SO /
	Planning sheet logic and confuse boards; it does not delete data by itself.
	"""
	if frappe.flags.in_test:
		return
	try:
		apps = frappe.get_installed_apps() or []
	except Exception:
		return
	if "production_entry" in apps and "production_scheduler" in apps:
		frappe.log_error(
			message=(
				"Both `production_scheduler` and `production_entry` are installed on this site. "
				"Remove `production_scheduler` after you confirm `production_entry` so hooks run once; "
				"otherwise behaviour (not raw row loss) may differ for Planning sheet / Sales Order."
			),
			title="production_entry: duplicate scheduler apps installed",
		)


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


def _sync_production_queue_custom_block():
	"""
	Restore the Apr 2026 POC «production queue» board from app asset
	``public/html/production_queue_block.html`` into ``Custom HTML Block`` ``production-queue``
	so Workspace pages that embed this block keep working after deploy.
	"""
	if frappe.flags.in_test:
		return
	if not frappe.db.table_exists("tabCustom HTML Block"):
		return
	app = "production_entry"
	path = frappe.get_app_path(app, "public", "html", "production_queue_block.html")
	try:
		with open(path, encoding="utf-8") as f:
			html = f.read()
	except OSError:
		frappe.log_error(
			frappe.get_traceback(),
			"production_entry: could not read production_queue_block.html",
		)
		return
	name = "production-queue"
	if frappe.db.exists("Custom HTML Block", name):
		current = frappe.db.get_value("Custom HTML Block", name, "html") or ""
		if current.strip() == html.strip():
			return
		doc = frappe.get_doc("Custom HTML Block", name)
		doc.html = html
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc(
			{"doctype": "Custom HTML Block", "name": name, "html": html}
		)
		doc.insert(ignore_permissions=True)


def _ensure_workspace_shows_production_queue():
	"""If ``Production Entry Desk`` exists, embed Custom HTML Block ``production-queue`` once."""
	if frappe.flags.in_test:
		return
	if not frappe.db.exists("Workspace", WORKSPACE_PRODUCTION_ENTRY_DESK):
		return
	if not frappe.db.exists("Custom HTML Block", "production-queue"):
		return
	doc = frappe.get_doc("Workspace", WORKSPACE_PRODUCTION_ENTRY_DESK)
	raw = doc.content or "[]"
	if isinstance(raw, str):
		try:
			content = json.loads(raw)
		except Exception:
			content = []
	else:
		content = list(raw)
	has_block = any(
		b.get("type") == "custom_block"
		and b.get("data", {}).get("custom_block_name") == "production-queue"
		for b in content
	)
	changed = False
	if not has_block:
		content.append(
			{
				"id": "pe-desk-queue",
				"source": "production_entry_desk",
				"type": "custom_block",
				"data": {"custom_block_name": "production-queue", "col": 12},
			}
		)
		doc.content = json.dumps(content)
		changed = True
	linked = {row.custom_block_name for row in (doc.custom_blocks or [])}
	if "production-queue" not in linked:
		doc.append(
			"custom_blocks",
			{"custom_block_name": "production-queue", "label": "Production queue"},
		)
		changed = True
	if changed:
		doc.save(ignore_permissions=True)


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
