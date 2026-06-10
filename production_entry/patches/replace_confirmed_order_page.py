# -*- coding: utf-8 -*-
"""Remove broken confirmed-order Page and point workspaces to confirm-orders."""
import json

import frappe


def _ensure_confirm_orders_page():
	"""Create/sync confirm-orders Page before workspace links are repointed."""
	if frappe.db.exists("Page", "confirm-orders"):
		return
	try:
		frappe.reload_doc("production_planning", "page", "confirm_orders")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "replace_confirmed_order_page: reload_doc")
	if frappe.db.exists("Page", "confirm-orders"):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Page",
			"name": "confirm-orders",
			"page_name": "confirm-orders",
			"title": "Confirm Orders",
			"module": "Production Planning",
			"standard": "Yes",
			"roles": [
				{"role": "System Manager"},
				{"role": "CRM TEAM"},
				{"role": "CRM MANAGER"},
				{"role": "Manufacturing User"},
				{"role": "Manufacturing Manager"},
			],
		}
	)
	doc.insert(ignore_permissions=True)


def _patch_workspace_links(ws_name):
	if not frappe.db.exists("Workspace", ws_name):
		return
	ws = frappe.get_doc("Workspace", ws_name)
	changed = False

	for row in ws.shortcuts or []:
		if row.link_to == "confirmed-order":
			row.link_to = "confirm-orders"
			if row.label == "Confirmed Order":
				row.label = "Confirm Orders"
			changed = True

	for row in ws.links or []:
		if row.link_to == "confirmed-order":
			row.link_to = "confirm-orders"
			if row.label == "Confirmed Order":
				row.label = "Confirm Orders"
			changed = True

	if ws.content:
		try:
			blocks = json.loads(ws.content)
			for block in blocks:
				data = block.get("data") or {}
				if data.get("shortcut_url") == "confirmed-order":
					data["shortcut_url"] = "confirm-orders"
					if data.get("label") == "Confirmed Order":
						data["label"] = "Confirm Orders"
					if data.get("shortcut_name") == "Confirmed Order":
						data["shortcut_name"] = "Confirm Orders"
					changed = True
			if changed:
				ws.content = json.dumps(blocks)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"replace_confirmed_order_page: {ws_name}")

	if changed:
		ws.flags.ignore_links = True
		ws.save(ignore_permissions=True)


def execute():
	# Page must exist before workspace links are updated (LinkValidationError otherwise).
	_ensure_confirm_orders_page()

	for ws_name in (
		"Confirmed Order List",
		"Production Scheduler",
		"Production Entry Desk",
	):
		_patch_workspace_links(ws_name)

	if frappe.db.exists("Page", "confirmed-order"):
		try:
			frappe.delete_doc("Page", "confirmed-order", force=1)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "replace_confirmed_order_page: delete old page")

	frappe.clear_cache()
	frappe.db.commit()
