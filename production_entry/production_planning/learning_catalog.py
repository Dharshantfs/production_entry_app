# -*- coding: utf-8 -*-
"""
Production Learning catalog — fabric processes (Phase 1).

BOM chains and sort ranks mirror scheduler_api post-sync (_PRODUCTION_SORT_RANK_BY_PROCESS).
Phase 2: add entries with phase="bag" (221–226, 211–217, 200–203).
"""

from __future__ import annotations

import frappe
from frappe import _

# Mirror scheduler_api._PRODUCTION_SORT_RANK_BY_PROCESS (fabric subset)
SORT_RANK = {
	"100": 10,
	"PB": 20,
	"102": 30,
	"103": 40,
	"104": 50,
	"105": 55,
	"107": 60,
	"106": 70,
	"109": 75,
	"251": 80,
	"252": 90,
	"253": 95,
	"254": 100,
	"255": 105,
	"108": 110,
}

RECOMMENDED_LEARNING_PATH = ["100", "103", "104", "107", "255"]

ACTION_LABELS = {
	"plan": "Plan",
	"produce": "Produce",
	"transfer": "Transfer",
	"despatch": "Despatch",
}


def _name(code: str, default: str) -> str:
	return frappe._(default)


def _chain_label(codes: list) -> str:
	if not codes:
		return ""
	return " → ".join(codes)


def _build_walkthrough_steps(fg_code: str, bom_chain: list, fg_is_so_line: bool = True) -> list:
	"""Micro-steps for animation: upstream children first, then FG."""
	steps = []
	for child in bom_chain:
		row = {
			"node_code": child,
			"node_role": "child",
			"actions": ["plan", "produce", "transfer"],
		}
		steps.append(row)
	if fg_is_so_line:
		steps.append(
			{
				"node_code": fg_code,
				"node_role": "fg",
				"actions": ["plan", "produce", "despatch"],
			}
		)
	return steps


def _slides_for_process(entry: dict) -> list:
	code = entry["code"]
	name = entry["name"]
	chain = entry.get("bom_chain") or []
	chain_txt = _chain_label(chain) if chain else _("none — this is the base material")
	tagline = entry.get("tagline") or ""
	prereq = entry.get("prerequisite_hint") or ""

	intro_body = _(
		"When you add process <b>{0}</b> ({1}) on the Sales Order, the Planning Sheet can add related items from the BOM on the same order line."
	).format(code, name)
	if chain:
		intro_body = _(
			"To produce <b>{0}</b> ({1}), the system expands the BOM and adds upstream items first — typically <b>{2}</b>."
		).format(code, name, chain_txt.replace(" → ", ", then "))

	priority_items = list(chain) + [code]
	priority_body = _(
		"Plan and produce in this order (upstream first): <b>{0}</b>."
	).format(" → ".join(priority_items))

	slides = [
		{
			"id": "intro",
			"title": _("Introduction"),
			"subtitle": tagline,
			"body_html": intro_body,
		},
		{
			"id": "bom",
			"title": _("BOM expansion"),
			"subtitle": _("What the Planning Sheet adds automatically"),
			"body_html": _(
				"Finished good <b>{0}</b> at the top; BOM children appear below on the same Sales Order line."
			).format(code),
			"tree": {"fg": code, "children": chain},
		},
		{
			"id": "priority",
			"title": _("Production priority"),
			"subtitle": _("What to plan and produce first"),
			"body_html": priority_body,
			"timeline": priority_items,
		},
		{
			"id": "walkthrough",
			"title": _("Walkthrough"),
			"subtitle": _("Plan → Produce → Transfer or Despatch"),
			"body_html": _(
				"BOM child rows use <b>Transfer</b> to the next unit. The Sales Order finished-good line uses <b>Despatch</b> when complete."
			),
			"steps": entry.get("walkthrough_steps") or [],
		},
		{
			"id": "summary",
			"title": _("Summary"),
			"subtitle": _("Before you go"),
			"body_html": prereq or _("Follow the order above on your Planning Sheet and boards."),
			"checklist": entry.get("checklist") or [],
			"shortcuts": entry.get("shortcuts") or [],
		},
	]
	return slides


# Phase 1 fabric catalog (code → entry). PB is a BOM child, included for completeness.
_FABRIC_ENTRIES = [
	{
		"code": "100",
		"name": _name("100", "Fabric"),
		"phase": "fabric",
		"role": "fabric",
		"tags": ["base"],
		"tagline": _("Base material — most processes start here"),
		"summary": _("Raw fabric rolls; plan and produce before lamination, slitting, or rewinding."),
		"bom_chain": [],
		"sort_rank": SORT_RANK["100"],
		"prerequisite_hint": _("Fabric 100 is planned first when it appears as a BOM child on another line."),
		"checklist": [
			_("Confirm fabric item and qty on the Planning Sheet"),
			_("Complete production on the fabric queue / color chart"),
			_("Use Transfer when moving to the next process unit"),
		],
		"shortcuts": [
			{"label": _("Color Chart"), "route": "/app/color-chart"},
			{"label": _("Planning Sheet"), "route": "/app/planning-sheet"},
		],
		"walkthrough_steps": [
			{"node_code": "100", "node_role": "fabric", "actions": ["plan", "produce", "transfer"]},
		],
	},
	{
		"code": "PB",
		"name": _name("PB", "Printed BOPP"),
		"phase": "fabric",
		"role": "child",
		"tags": ["bopp"],
		"tagline": _("Printed BOPP film from the 107 BOM"),
		"summary": _("Added with BOPP lamination (107); plan after fabric 100 when both are on the sheet."),
		"bom_chain": [],
		"sort_rank": SORT_RANK["PB"],
		"prerequisite_hint": _("Usually appears on the same SO line as process 107 — complete 100 and PB before finishing 107."),
		"checklist": [_("Check PB row exists on Planning Sheet when 107 FG is on the order")],
		"shortcuts": [{"label": _("Printed BOPP Film Board"), "route": "/app/printed-bopp-film-board"}],
		"walkthrough_steps": [
			{"node_code": "PB", "node_role": "child", "actions": ["plan", "produce", "transfer"]},
		],
	},
	{
		"code": "102",
		"name": _name("102", "Rewinding"),
		"phase": "fabric",
		"role": "fg",
		"tags": ["mid"],
		"tagline": _("Rewinding needs fabric 100 from BOM"),
		"summary": _("Needs fabric 100 first"),
		"bom_chain": ["100"],
		"sort_rank": SORT_RANK["102"],
		"prerequisite_hint": _("Complete fabric 100 before you plan and produce rewinding 102."),
		"checklist": [_("Fabric 100 row is on the same SO line"), _("Rewinding board shows 102 parent")],
		"shortcuts": [
			{"label": _("Rewinding Board"), "route": "/app/rewinding-board"},
			{"label": _("Planning Sheet"), "route": "/app/planning-sheet"},
		],
		"walkthrough_steps": _build_walkthrough_steps("102", ["100"]),
	},
	{
		"code": "103",
		"name": _name("103", "Slitting"),
		"phase": "fabric",
		"role": "fg",
		"tags": ["mid"],
		"tagline": _("Slitting pulls fabric 100 from BOM"),
		"summary": _("Needs fabric 100 first"),
		"bom_chain": ["100"],
		"sort_rank": SORT_RANK["103"],
		"prerequisite_hint": _("Complete fabric 100 before slitting 103."),
		"checklist": [_("Fabric child row added from BOM"), _("Slitting unit assigned on sheet")],
		"shortcuts": [
			{"label": _("Slitting Board"), "route": "/app/slitting-board"},
			{"label": _("Planning Sheet"), "route": "/app/planning-sheet"},
		],
		"walkthrough_steps": _build_walkthrough_steps("103", ["100"]),
	},
	{
		"code": "104",
		"name": _name("104", "Lamination"),
		"phase": "fabric",
		"role": "fg",
		"tags": ["mid"],
		"tagline": _("Lamination needs fabric 100 from BOM"),
		"summary": _("Needs fabric 100 first"),
		"bom_chain": ["100"],
		"sort_rank": SORT_RANK["104"],
		"prerequisite_hint": _("Complete fabric 100 before you plan and produce lamination 104."),
		"checklist": [
			_("Fabric 100 planned and produced on this SO line"),
			_("104 row on Lamination board / order table"),
			_("Parent Child Trace ID matches across 100 and 104"),
		],
		"shortcuts": [
			{"label": _("Lamination Board"), "route": "/app/lamination-board"},
			{"label": _("Planning Sheet"), "route": "/app/planning-sheet"},
		],
		"walkthrough_steps": _build_walkthrough_steps("104", ["100"]),
	},
	{
		"code": "105",
		"name": _name("105", "Printing"),
		"phase": "fabric",
		"role": "fg",
		"tags": ["mid"],
		"tagline": _("Flexo printing needs fabric 100"),
		"summary": _("Needs fabric 100 first"),
		"bom_chain": ["100"],
		"sort_rank": SORT_RANK["105"],
		"prerequisite_hint": _("Complete fabric 100 before printing 105."),
		"checklist": [_("105 on printing queue"), _("Design code stamped when applicable")],
		"shortcuts": [
			{"label": _("Printing Board"), "route": "/app/printing-order-board"},
			{"label": _("Planning Sheet"), "route": "/app/planning-sheet"},
		],
		"walkthrough_steps": _build_walkthrough_steps("105", ["100"]),
	},
	{
		"code": "106",
		"name": _name("106", "Sheet printing"),
		"phase": "fabric",
		"role": "fg",
		"tags": ["mid", "sheet"],
		"tagline": _("Often part of 254 sheet chain: 106 → 104 → 100"),
		"summary": _("In stage-3 sheets: needs 104 and 100 below"),
		"bom_chain": ["100", "104"],
		"sort_rank": SORT_RANK["106"],
		"prerequisite_hint": _("For 254 FG: complete 100, then 104, then 106 before the 254 FG line."),
		"checklist": [_("104 and 100 children present when 106 is BOM-expanded")],
		"shortcuts": [
			{"label": _("Printing Board"), "route": "/app/printing-order-board"},
			{"label": _("Planning Sheet"), "route": "/app/planning-sheet"},
		],
		"walkthrough_steps": _build_walkthrough_steps("106", ["100", "104"]),
	},
	{
		"code": "107",
		"name": _name("107", "BOPP lamination"),
		"phase": "fabric",
		"role": "fg",
		"tags": ["bopp", "mid"],
		"tagline": _("BOPP lam adds fabric 100 and Printed BOPP (PB)"),
		"summary": _("Needs 100 and PB from BOM"),
		"bom_chain": ["100", "PB"],
		"sort_rank": SORT_RANK["107"],
		"prerequisite_hint": _("Complete fabric 100 and PB rows before finishing 107."),
		"checklist": [_("100* and PB-* children on Planning Sheet"), _("107 on lamination unit")],
		"shortcuts": [
			{"label": _("Lamination Board"), "route": "/app/lamination-board"},
			{"label": _("Planning Sheet"), "route": "/app/planning-sheet"},
		],
		"walkthrough_steps": _build_walkthrough_steps("107", ["100", "PB"]),
	},
	{
		"code": "108",
		"name": _name("108", "BOPP lam slitting"),
		"phase": "fabric",
		"role": "fg",
		"tags": ["bopp"],
		"tagline": _("108 expands to 107, then 100 and PB"),
		"summary": _("Chain: 107 → 100 + PB"),
		"bom_chain": ["100", "PB", "107"],
		"sort_rank": SORT_RANK["108"],
		"prerequisite_hint": _("Work through 100, PB, 107, then 108 on the same SO line."),
		"checklist": [_("107 child row from 108 BOM"), _("Fabric and PB children under 107")],
		"shortcuts": [
			{"label": _("Lamination Board"), "route": "/app/lamination-board"},
			{"label": _("Planning Sheet"), "route": "/app/planning-sheet"},
		],
		"walkthrough_steps": _build_walkthrough_steps("108", ["100", "PB", "107"]),
	},
	{
		"code": "109",
		"name": _name("109", "Lam slitting FG"),
		"phase": "fabric",
		"role": "fg",
		"tags": ["mid"],
		"tagline": _("109 laminated slitting adds 104 then 100"),
		"summary": _("Needs 104 → 100"),
		"bom_chain": ["100", "104"],
		"sort_rank": SORT_RANK["109"],
		"prerequisite_hint": _("Complete 100, then 104, before 109 FG."),
		"checklist": [_("104 lamination child on sheet"), _("100 fabric from 104 BOM")],
		"shortcuts": [
			{"label": _("Slitting Board"), "route": "/app/slitting-board"},
			{"label": _("Planning Sheet"), "route": "/app/planning-sheet"},
		],
		"walkthrough_steps": _build_walkthrough_steps("109", ["100", "104"]),
	},
	{
		"code": "251",
		"name": _name("251", "Direct sheet cutting"),
		"phase": "fabric",
		"role": "fg",
		"tags": ["sheet"],
		"tagline": _("Sheet cutting 251 adds fabric 100"),
		"summary": _("Needs fabric 100 first"),
		"bom_chain": ["100"],
		"sort_rank": SORT_RANK["251"],
		"prerequisite_hint": _("Complete fabric 100 before sheet cutting 251."),
		"checklist": [_("251 on sheet cutting board"), _("100 child from BOM")],
		"shortcuts": [
			{"label": _("Sheet Cutting Board"), "route": "/app/sheet-cutting-board"},
			{"label": _("Planning Sheet"), "route": "/app/planning-sheet"},
		],
		"walkthrough_steps": _build_walkthrough_steps("251", ["100"]),
	},
	{
		"code": "252",
		"name": _name("252", "Design sheet"),
		"phase": "fabric",
		"role": "fg",
		"tags": ["sheet"],
		"tagline": _("252 adds printing 105 then fabric 100"),
		"summary": _("Chain: 105 → 100"),
		"bom_chain": ["100", "105"],
		"sort_rank": SORT_RANK["252"],
		"prerequisite_hint": _("Complete 100, then 105, before 252 FG."),
		"checklist": [_("105 printing child"), _("100 fabric under 105")],
		"shortcuts": [
			{"label": _("Sheet Cutting Board"), "route": "/app/sheet-cutting-board"},
			{"label": _("Planning Sheet"), "route": "/app/planning-sheet"},
		],
		"walkthrough_steps": _build_walkthrough_steps("252", ["100", "105"]),
	},
	{
		"code": "253",
		"name": _name("253", "Laminated sheet"),
		"phase": "fabric",
		"role": "fg",
		"tags": ["sheet"],
		"tagline": _("253 adds lamination 104 then fabric 100"),
		"summary": _("Chain: 104 → 100"),
		"bom_chain": ["100", "104"],
		"sort_rank": SORT_RANK["253"],
		"prerequisite_hint": _("Complete 100, then 104, before 253."),
		"checklist": [_("104 child from 253 BOM")],
		"shortcuts": [
			{"label": _("Sheet Cutting Board"), "route": "/app/sheet-cutting-board"},
			{"label": _("Planning Sheet"), "route": "/app/planning-sheet"},
		],
		"walkthrough_steps": _build_walkthrough_steps("253", ["100", "104"]),
	},
	{
		"code": "254",
		"name": _name("254", "Lam sheet FG"),
		"phase": "fabric",
		"role": "fg",
		"tags": ["sheet"],
		"tagline": _("254 stage-3 chain: 106 → 104 → 100"),
		"summary": _("Longest fabric sheet chain"),
		"bom_chain": ["100", "104", "106"],
		"sort_rank": SORT_RANK["254"],
		"prerequisite_hint": _("Complete 100, then 104, then 106, before 254 finished good."),
		"checklist": [
			_("106 printing child on sheet"),
			_("104 under 106"),
			_("100 fabric at bottom of chain"),
		],
		"shortcuts": [
			{"label": _("Sheet Cutting Board"), "route": "/app/sheet-cutting-board"},
			{"label": _("Printing Board"), "route": "/app/printing-order-board"},
			{"label": _("Planning Sheet"), "route": "/app/planning-sheet"},
		],
		"walkthrough_steps": _build_walkthrough_steps("254", ["100", "104", "106"]),
	},
	{
		"code": "255",
		"name": _name("255", "BOPP lam sheet"),
		"phase": "fabric",
		"role": "fg",
		"tags": ["bopp", "sheet"],
		"tagline": _("255 adds 107, then 100 and PB"),
		"summary": _("BOPP sheet FG — 107 → 100 + PB"),
		"bom_chain": ["100", "PB", "107"],
		"sort_rank": SORT_RANK["255"],
		"prerequisite_hint": _("Complete 100 and PB, then 107, before 255 sheet FG."),
		"checklist": [
			_("107 BOPP lam child"),
			_("100 and PB under 107"),
			_("255 on sheet cutting when applicable"),
		],
		"shortcuts": [
			{"label": _("Sheet Cutting Board"), "route": "/app/sheet-cutting-board"},
			{"label": _("Lamination Board"), "route": "/app/lamination-board"},
			{"label": _("Planning Sheet"), "route": "/app/planning-sheet"},
		],
		"walkthrough_steps": _build_walkthrough_steps("255", ["100", "PB", "107"]),
	},
]

_CATALOG_BY_CODE = {e["code"]: e for e in _FABRIC_ENTRIES}


def get_catalog_entries(phase: str = "fabric") -> list[dict]:
	"""Return catalog rows for API (summary fields only)."""
	phase = (phase or "fabric").strip().lower()
	out = []
	for e in _FABRIC_ENTRIES:
		if phase and e.get("phase") != phase:
			continue
		chain = e.get("bom_chain") or []
		out.append(
			{
				"code": e["code"],
				"name": e["name"],
				"phase": e["phase"],
				"role": e["role"],
				"tags": e.get("tags") or [],
				"tagline": e.get("tagline") or "",
				"summary": e.get("summary") or "",
				"bom_chain": chain,
				"chain_label": _chain_label(chain) if chain else "",
				"sort_rank": e.get("sort_rank") or 999,
			}
		)
	out.sort(key=lambda x: (x.get("sort_rank") or 999, x.get("code") or ""))
	return out


def get_lesson(process_code: str) -> dict | None:
	"""Full lesson payload for one process."""
	code = (process_code or "").strip().upper()
	if code == "PB":
		entry = _CATALOG_BY_CODE.get("PB")
	elif code.isdigit() or code in _CATALOG_BY_CODE:
		entry = _CATALOG_BY_CODE.get(code) or _CATALOG_BY_CODE.get(code.lstrip("0"))
	else:
		entry = _CATALOG_BY_CODE.get(code)
	if not entry:
		return None
	lesson = dict(entry)
	lesson["slides"] = _slides_for_process(entry)
	lesson["recommended_path"] = RECOMMENDED_LEARNING_PATH
	lesson["action_labels"] = ACTION_LABELS
	return lesson


def get_recommended_path() -> list[str]:
	return list(RECOMMENDED_LEARNING_PATH)
