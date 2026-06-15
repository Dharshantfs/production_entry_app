# -*- coding: utf-8 -*-
"""Ensure Planning workspace exists with Confirm Orders, Planning Sheet, and Production Plan."""
import json

import frappe


WORKSPACE_NAME = "Planning"

_PLANNING_LINKS = (
	{
		"type": "Link",
		"label": "Confirm Orders",
		"link_type": "Page",
		"link_to": "confirm-orders",
		"icon": "tick",
		"description": "Review and confirm sales orders for planning",
		"onboard": 1,
		"hidden": 0,
		"is_query_report": 0,
		"link_count": 0,
	},
	{
		"type": "Link",
		"label": "Planning Sheet",
		"link_type": "DocType",
		"link_to": "Planning sheet",
		"icon": "list",
		"description": "Party-wise planning sheet and line items",
		"onboard": 1,
		"hidden": 0,
		"is_query_report": 0,
		"link_count": 0,
	},
	{
		"type": "Link",
		"label": "Production Plan",
		"link_type": "DocType",
		"link_to": "Production Plan",
		"icon": "project",
		"description": "Production plans and work order generation",
		"onboard": 1,
		"hidden": 0,
		"is_query_report": 0,
		"link_count": 0,
	},
)

_PLANNING_SHORTCUTS = (
	{
		"label": "Confirm Orders",
		"link_to": "confirm-orders",
		"type": "Page",
		"icon": "tick",
		"color": "Green",
	},
	{
		"label": "Planning Sheet",
		"link_to": "Planning sheet",
		"type": "DocType",
		"icon": "list",
		"color": "Blue",
		"doc_view": "List",
	},
	{
		"label": "Production Plan",
		"link_to": "Production Plan",
		"type": "DocType",
		"icon": "project",
		"color": "Orange",
		"doc_view": "List",
	},
)

_PLANNING_CONTENT = [
	{
		"id": "confirm_orders_shortcut",
		"type": "shortcut",
		"data": {
			"shortcut_name": "Confirm Orders",
			"shortcut_type": "Page",
			"shortcut_url": "confirm-orders",
			"label": "Confirm Orders",
			"icon": "tick",
			"col": 4,
		},
	},
	{
		"id": "planning_sheet_shortcut",
		"type": "shortcut",
		"data": {
			"shortcut_name": "Planning sheet",
			"shortcut_type": "DocType",
			"shortcut_url": "Planning sheet",
			"label": "Planning Sheet",
			"icon": "list",
			"col": 4,
		},
	},
	{
		"id": "production_plan_shortcut",
		"type": "shortcut",
		"data": {
			"shortcut_name": "Production Plan",
			"shortcut_type": "DocType",
			"shortcut_url": "Production Plan",
			"label": "Production Plan",
			"icon": "project",
			"col": 4,
		},
	},
]


def _sync_planning_workspace_doc(ws):
	changed = False
	existing_links = {(row.link_type, row.link_to) for row in (ws.links or [])}
	for row in _PLANNING_LINKS:
		key = (row["link_type"], row["link_to"])
		if key not in existing_links:
			ws.append("links", row)
			changed = True

	existing_shortcuts = {(row.type, row.link_to) for row in (ws.shortcuts or [])}
	for row in _PLANNING_SHORTCUTS:
		key = (row["type"], row["link_to"])
		if key not in existing_shortcuts:
			ws.append("shortcuts", row)
			changed = True

	try:
		content = json.loads(ws.content or "[]")
	except Exception:
		content = []
	content_ids = {block.get("id") for block in content}
	for block in _PLANNING_CONTENT:
		if block["id"] not in content_ids:
			content.append(block)
			changed = True
	if changed:
		ws.content = json.dumps(content)

	if ws.icon != "project":
		ws.icon = "project"
		changed = True
	if ws.label != WORKSPACE_NAME:
		ws.label = WORKSPACE_NAME
		changed = True
	if ws.title != WORKSPACE_NAME:
		ws.title = WORKSPACE_NAME
		changed = True
	if not ws.public:
		ws.public = 1
		changed = True
	if ws.is_hidden:
		ws.is_hidden = 0
		changed = True

	return changed


def execute():
	try:
		frappe.reload_doc("production_planning", "workspace", "planning")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "ensure_planning_workspace: reload_doc")

	if not frappe.db.exists("Workspace", WORKSPACE_NAME):
		try:
			frappe.reload_doc("production_planning", "workspace", "planning")
		except Exception:
			frappe.log_error(frappe.get_traceback(), "ensure_planning_workspace: second reload")

	if frappe.db.exists("Workspace", WORKSPACE_NAME):
		ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
		if _sync_planning_workspace_doc(ws):
			ws.flags.ignore_links = True
			ws.save(ignore_permissions=True)

	frappe.clear_cache()
