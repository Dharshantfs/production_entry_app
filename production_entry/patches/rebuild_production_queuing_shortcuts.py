# -*- coding: utf-8 -*-
"""Rebuild Production Queuing with clickable Page shortcuts (no Custom HTML Block).

Previous fix only rendered a plain header because Custom HTML Blocks often fail
silently on Frappe Cloud / v16. Native workspace shortcuts are reliable links.
"""
from __future__ import annotations

import json

import frappe

WORKSPACE_ALIASES = (
	"Production Queuing",
	"Production Queue",
	"production-queuing",
)

# label, page route, icon (optional)
BOARD_SHORTCUTS = (
	("Production Board", "production-board", "gantt"),
	("Lamination Board", "lamination-board", "organization"),
	("Color Chart", "color-chart", "color"),
	("Production Table", "production-table", "table"),
	("GSM Production Entry", "gsm-production-entry", "edit"),
	("Printing Order Board", "printing-order-board", "printer"),
	("Slitting Board", "slitting-board", "cut"),
	("Rewinding Board", "rewinding-board", "refresh"),
	("Sheet Cutting Board", "sheet-cutting-board", "file"),
	("Printed BOPP Film Board", "printed-bopp-film-board", "image-view"),
	("Box Bag Board", "box-bag-board", "retail"),
	("W CUT / D CUT Board", "w-cut-d-cut-board", "organization"),
	("Logistics Kanban", "logistics-kanban", "truck"),
)


def _content_json() -> str:
	blocks = [
		{
			"id": "pq-h1",
			"type": "header",
			"data": {"text": "Open a board", "col": 12},
		}
	]
	for label, _route, _icon in BOARD_SHORTCUTS:
		sid = "pq-" + label.lower().replace(" ", "-").replace("/", "-")[:40]
		blocks.append(
			{
				"id": sid,
				"type": "shortcut",
				"data": {
					"shortcut_name": label,
					"shortcut_type": "Page",
					"col": 3,
				},
			}
		)
	return json.dumps(blocks)


def _apply_shortcuts(doc) -> None:
	"""Replace workspace shortcuts + sidebar links with board pages."""
	doc.set("shortcuts", [])
	for label, route, icon in BOARD_SHORTCUTS:
		if not frappe.db.exists("Page", route):
			continue
		row = {"label": label, "link_to": route, "type": "Page"}
		# Some sites have icon on shortcut child
		try:
			doc.append("shortcuts", row)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"pq_shortcut_{label}")

	# Sidebar links (Link cards)
	if hasattr(doc, "links"):
		doc.set("links", [])
		doc.append(
			"links",
			{
				"type": "Card Break",
				"label": "Production boards",
				"hidden": 0,
			},
		)
		for label, route, icon in BOARD_SHORTCUTS:
			if not frappe.db.exists("Page", route):
				continue
			doc.append(
				"links",
				{
					"type": "Link",
					"label": label,
					"link_type": "Page",
					"link_to": route,
					"icon": icon,
					"hidden": 0,
					"onboard": 1,
				},
			)


def _fix_workspace(name: str) -> None:
	doc = frappe.get_doc("Workspace", name)
	_apply_shortcuts(doc)
	doc.content = _content_json()
	# Drop broken custom block dependency from this workspace
	if hasattr(doc, "custom_blocks"):
		doc.set("custom_blocks", [])
	if hasattr(doc, "public"):
		doc.public = 1
	if hasattr(doc, "is_hidden"):
		doc.is_hidden = 0
	doc.flags.ignore_permissions = True
	doc.flags.ignore_links = True
	doc.flags.ignore_validate = True
	doc.save(ignore_permissions=True)


def execute():
	found = False
	for name in WORKSPACE_ALIASES:
		if frappe.db.exists("Workspace", name):
			_fix_workspace(name)
			found = True

	if not found:
		ws = frappe.get_doc(
			{
				"doctype": "Workspace",
				"label": "Production Queuing",
				"title": "Production Queuing",
				"module": "Production Planning",
				"public": 1,
				"is_hidden": 0,
				"content": "[]",
			}
		)
		ws.insert(ignore_permissions=True)
		_fix_workspace(ws.name)

	frappe.clear_cache()
	frappe.db.commit()
