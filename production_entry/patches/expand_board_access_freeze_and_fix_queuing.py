# -*- coding: utf-8 -*-
"""Expand Allowed Boards freeze fields and repair Production Queuing launcher."""
from __future__ import annotations

import json
import os

import frappe
from frappe.modules.import_file import import_file_by_path

from production_entry.install import _sync_production_queue_custom_block

WORKSPACE_ALIASES = (
	"Production Queuing",
	"Production Queue",
	"production-queuing",
)


def _import_board_child():
	path = frappe.get_app_path(
		"production_entry",
		"production_planning",
		"doctype",
		"production_board_access_board",
		"production_board_access_board.json",
	)
	if os.path.exists(path):
		import_file_by_path(path, force=True)


def _workspace_content() -> str:
	return json.dumps(
		[
			{
				"id": "pq-launcher",
				"type": "custom_block",
				"data": {"custom_block_name": "production-queue", "col": 12},
			}
		]
	)


def _fix_production_queuing():
	_sync_production_queue_custom_block()
	if frappe.db.exists("Custom HTML Block", "production-queue"):
		doc = frappe.get_doc("Custom HTML Block", "production-queue")
		if doc.get("roles"):
			doc.set("roles", [])
			doc.flags.ignore_permissions = True
			doc.save(ignore_permissions=True)

	for name in WORKSPACE_ALIASES:
		if not frappe.db.exists("Workspace", name):
			continue
		ws = frappe.get_doc("Workspace", name)
		if hasattr(ws, "shortcuts"):
			ws.set("shortcuts", [])
		ws.content = _workspace_content()
		linked = {row.custom_block_name for row in (ws.custom_blocks or [])}
		if "production-queue" not in linked:
			ws.append(
				"custom_blocks",
				{"custom_block_name": "production-queue", "label": "Production queue"},
			)
		if hasattr(ws, "public"):
			ws.public = 1
		if hasattr(ws, "is_hidden"):
			ws.is_hidden = 0
		ws.flags.ignore_permissions = True
		ws.flags.ignore_links = True
		ws.flags.ignore_validate = True
		ws.save(ignore_permissions=True)


def execute():
	_import_board_child()
	_fix_production_queuing()
	frappe.clear_cache()
	frappe.db.commit()
