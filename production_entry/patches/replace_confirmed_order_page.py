# -*- coding: utf-8 -*-
"""Remove broken confirmed-order Page and point workspaces to confirm-orders."""
import json

import frappe


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
		ws.save(ignore_permissions=True)


def execute():
	if frappe.db.exists("Page", "confirmed-order"):
		try:
			frappe.delete_doc("Page", "confirmed-order", force=1)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "replace_confirmed_order_page: delete old page")

	for ws_name in (
		"Confirmed Order List",
		"Production Scheduler",
		"Production Entry Desk",
	):
		_patch_workspace_links(ws_name)

	frappe.clear_cache()
	frappe.db.commit()
