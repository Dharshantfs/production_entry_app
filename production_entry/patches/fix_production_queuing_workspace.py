# -*- coding: utf-8 -*-
"""Fix blank Production Queuing workspace — sync Custom HTML Block + workspace content."""
from __future__ import annotations

import json

import frappe

from production_entry.install import (
	_ensure_workspace_shows_production_queue,
	_sync_production_queue_custom_block,
)

WORKSPACE_ALIASES = (
	"Production Queuing",
	"Production Queue",
	"production-queuing",
)


def _workspace_content_with_block(title: str = "Production Queuing") -> str:
	return json.dumps(
		[
			{
				"id": "pq-header",
				"type": "header",
				"data": {"text": title, "col": 12},
			},
			{
				"id": "pq-queue-block",
				"type": "custom_block",
				"data": {"custom_block_name": "production-queue", "col": 12},
			},
		]
	)


def _fix_production_queuing_workspace() -> None:
	for name in WORKSPACE_ALIASES:
		if not frappe.db.exists("Workspace", name):
			continue
		doc = frappe.get_doc("Workspace", name)
		doc.content = _workspace_content_with_block(doc.label or name)
		linked = {row.custom_block_name for row in (doc.custom_blocks or [])}
		if "production-queue" not in linked:
			doc.append(
				"custom_blocks",
				{"custom_block_name": "production-queue", "label": "Production queue"},
			)
		if hasattr(doc, "public"):
			doc.public = 1
		if hasattr(doc, "is_hidden"):
			doc.is_hidden = 0
		doc.flags.ignore_permissions = True
		doc.flags.ignore_links = True
		doc.save(ignore_permissions=True)
		return

	if not frappe.db.exists("Workspace", "Production Queuing"):
		ws = frappe.get_doc(
			{
				"doctype": "Workspace",
				"label": "Production Queuing",
				"title": "Production Queuing",
				"public": 1,
				"is_hidden": 0,
				"content": _workspace_content_with_block(),
				"custom_blocks": [
					{"custom_block_name": "production-queue", "label": "Production queue"}
				],
			}
		)
		ws.insert(ignore_permissions=True)


def _clear_custom_block_role_lock() -> None:
	"""Empty roles on production-queue block so operators can see it."""
	if not frappe.db.exists("Custom HTML Block", "production-queue"):
		return
	doc = frappe.get_doc("Custom HTML Block", "production-queue")
	if doc.get("roles"):
		doc.set("roles", [])
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)


def execute():
	_sync_production_queue_custom_block()
	_clear_custom_block_role_lock()
	_ensure_workspace_shows_production_queue()
	_fix_production_queuing_workspace()
	frappe.clear_cache()
	frappe.db.commit()
