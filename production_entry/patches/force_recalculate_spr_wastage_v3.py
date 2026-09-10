# -*- coding: utf-8 -*-
"""v3: hard force-recalculate wastage + recycle on known broken submitted SPRs."""
from __future__ import annotations

import frappe


def execute():
	from production_entry.production_planning.doctype.shaft_production_run.shaft_production_run import (
		force_recalculate_spr_wastage_and_recycle,
	)

	names = [
		"SPR-2026-00802",
		"SPR-2026-00809",
		"SPR-2026-00803",
		"SPR-2026-00799",
	]
	recent = frappe.get_all(
		"Shaft Production Run",
		filters={"docstatus": 1, "modified": [">=", "2026-09-01"]},
		pluck="name",
		order_by="modified desc",
		limit_page_length=50,
	) or []
	for n in recent:
		if n not in names:
			names.append(n)

	for name in names:
		if not frappe.db.exists("Shaft Production Run", name):
			continue
		try:
			res = force_recalculate_spr_wastage_and_recycle(name)
			frappe.db.commit()
			frappe.logger("production_entry").info(f"force_recalc_v3 {name}: {res}")
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"force_recalculate_spr_wastage_v3:{name}")
