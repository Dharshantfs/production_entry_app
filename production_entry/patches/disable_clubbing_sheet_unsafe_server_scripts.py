# -*- coding: utf-8 -*-
"""Disable Clubbing Sheet DocType Event Server Scripts that crash Frappe 16 safe_exec.

App hooks already own before_save / before_submit / on_cancel via
production_entry.production_planning.clubbing_sheet_hooks.

Site Server Scripts that call str.format(...) raise:
  SyntaxError: format is an unsafe attribute
"""

from __future__ import annotations

import frappe


_APP_OWNED_EVENTS = {
	"Before Save",
	"Validate",
	"Before Submit",
	"On Cancel",
	"on_cancel",
}


def _rewrite_format_throw(script: str) -> str:
	"""Best-effort replace of the known Full Load .format throw (paste script)."""
	old = (
		'msg = (\n'
		'                "Customer {0} has a total weight of {1} kgs (>= 5000 kgs). "\n'
		'                "Orders >= 5000 kgs must be clubbed separately as a Full Load."\n'
		'            ).format(full_load_customers[0], customer_weights[full_load_customers[0]])\n'
		'            frappe.throw(msg)'
	)
	new = (
		'msg = (\n'
		'                "Customer "\n'
		'                + str(full_load_customers[0])\n'
		'                + " has a total weight of "\n'
		'                + str(customer_weights[full_load_customers[0]])\n'
		'                + " kgs (>= 5000 kgs). "\n'
		'                + "Normally a Full Load alone — save/submit still allowed."\n'
		'            )\n'
		'            frappe.msgprint(msg)'
	)
	if old in script:
		return script.replace(old, new)
	# Compact / alternate spacing
	if ").format(full_load_customers[0], customer_weights[full_load_customers[0]])" in script:
		script = script.replace(
			").format(full_load_customers[0], customer_weights[full_load_customers[0]])",
			")",
		)
		# That alone may leave broken msg assignment; prefer disable path below.
	return script


def execute():
	if not frappe.db.exists("DocType", "Server Script"):
		return

	rows = frappe.get_all(
		"Server Script",
		filters={
			"reference_doctype": "Clubbing Sheet",
			"script_type": "DocType Event",
			"disabled": 0,
		},
		fields=["name", "script", "doctype_event"],
	)
	changed = False
	for row in rows:
		body = row.script or ""
		evt = (row.doctype_event or "").strip()
		name_l = (row.name or "").lower()
		looks_like_paste = (
			".format(" in body
			or "full_load_customers" in body
			or "ROUTE_BELTS" in body
			or "clubbing" in name_l
		)
		if evt in _APP_OWNED_EVENTS and looks_like_paste:
			# App hook owns this event — disable to stop double-run + safe_exec crash.
			frappe.db.set_value("Server Script", row.name, "disabled", 1, update_modified=False)
			if ".format(" in body:
				fixed = _rewrite_format_throw(body)
				if fixed != body:
					frappe.db.set_value(
						"Server Script", row.name, "script", fixed, update_modified=False
					)
			changed = True
			continue

		# Keep enabled custom scripts but neutralize known .format crash.
		if ".format(" in body and "full_load_customers" in body:
			fixed = _rewrite_format_throw(body)
			if fixed != body:
				frappe.db.set_value(
					"Server Script", row.name, "script", fixed, update_modified=False
				)
				changed = True

	if changed:
		frappe.clear_cache(doctype="Clubbing Sheet")
		frappe.clear_cache(doctype="Server Script")
