# -*- coding: utf-8 -*-
"""Sync Shaft Production Run Client Scripts so core/wastage do not dirty a submitted SPR."""
import os

import frappe


def execute():
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
	if not scripts:
		return

	for js_path, markers in pairs:
		if not os.path.exists(js_path):
			continue
		with open(js_path, "r", encoding="utf-8") as f:
			new_script = f.read()
		for row in scripts:
			doc = frappe.get_doc("Client Script", row.name)
			body = doc.script or ""
			if not any(m in body for m in markers):
				continue
			doc.script = new_script
			doc.enabled = 1
			doc.save(ignore_permissions=True)

	frappe.clear_cache(doctype="Shaft Production Run")
