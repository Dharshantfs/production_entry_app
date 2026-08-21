# -*- coding: utf-8 -*-
"""Production Queuing: remove leaked shortcuts; show only access-driven Custom HTML launcher."""
from __future__ import annotations

import json

import frappe

from production_entry.install import _sync_production_queue_custom_block

WORKSPACE_ALIASES = (
	"Production Queuing",
	"Production Queue",
	"production-queuing",
)


def _content() -> str:
	return json.dumps(
		[
			{
				"id": "pq-launcher",
				"type": "custom_block",
				"data": {"custom_block_name": "production-queue", "col": 12},
			}
		]
	)


def execute():
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
		# Wipe shortcut tiles that ignored Production Board Access (e.g. GSM leak).
		if hasattr(ws, "shortcuts"):
			ws.set("shortcuts", [])
		ws.content = _content()
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

	frappe.clear_cache()
	frappe.db.commit()
