# -*- coding: utf-8 -*-
"""Backfill Running Patty Wastage + Core Details on submitted SPRs missing them.

Also re-syncs desk Client Scripts so submitted SPR forms are not dirtied (Not Saved).
"""
from __future__ import annotations

import os

import frappe
from frappe.utils import cint


# Known empty SPRs from Unit 2 / Day / 2026-09-07 GSM submit session
_KNOWN_EMPTY = (
	"SPR-2026-00769",
	"SPR-2026-00772",
	"SPR-2026-00775",
	"SPR-2026-00776",
	"SPR-2026-00777",
)


def _sync_client_scripts():
	app_path = frappe.get_app_path("production_entry")
	pairs = (
		(
			os.path.join(app_path, "public", "js", "spr_site_core_automation.js"),
			("CORE DEBUG", "calculate_aggregate_totals"),
		),
		(
			os.path.join(app_path, "public", "js", "spr_site_wastage_automation.js"),
			("Wastage Automation", "Wastage Extra Width Debug"),
		),
	)
	scripts = frappe.get_all(
		"Client Script",
		filters={"dt": "Shaft Production Run"},
		fields=["name"],
	)
	for js_path, markers in pairs:
		if not os.path.exists(js_path):
			continue
		with open(js_path, "r", encoding="utf-8") as f:
			new_script = f.read()
		for row in scripts or []:
			doc = frappe.get_doc("Client Script", row.name)
			body = doc.script or ""
			if not any(m in body for m in markers):
				continue
			if body == new_script:
				continue
			doc.script = new_script
			doc.enabled = 1
			doc.save(ignore_permissions=True)
	frappe.clear_cache(doctype="Shaft Production Run")


def execute():
	_sync_client_scripts()

	from production_entry.production_planning.doctype.shaft_production_run.shaft_production_run import (
		persist_spr_patty_and_core,
	)

	names = set()
	for n in _KNOWN_EMPTY:
		if frappe.db.exists("Shaft Production Run", n):
			names.add(n)

	# Also any submitted Unit 2 / 2026-09-07 SPRs with empty patty table
	meta = frappe.get_meta("Shaft Production Run")
	filters = {"docstatus": 1}
	if meta.has_field("run_date"):
		filters["run_date"] = "2026-09-07"
	unit_field = "custom_unit" if meta.has_field("custom_unit") else None
	if unit_field:
		filters[unit_field] = ["like", "%UNIT 2%"]
	for n in frappe.get_all("Shaft Production Run", filters=filters, pluck="name", limit_page_length=100) or []:
		names.add(n)

	for name in sorted(names):
		try:
			persist_spr_patty_and_core(name, only_if_empty=True, save_if_draft=False)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"backfill_spr_patty_and_core:{name}")
