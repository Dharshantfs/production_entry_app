# -*- coding: utf-8 -*-
"""v4: restore Running Patty / Recycled on draft+submitted SPRs left at qty=0."""
from __future__ import annotations

import frappe


def execute():
	from production_entry.production_planning.doctype.shaft_production_run.shaft_production_run import (
		force_recalculate_spr_wastage_and_recycle,
	)

	names = [
		"SPR-2026-00814",
		"SPR-2026-00813",
		"SPR-2026-00802",
		"SPR-2026-00809",
		"SPR-2026-00803",
		"SPR-2026-00799",
	]
	# Recent drafts (GSM / recycle often leave zero wastage here)
	recent_draft = frappe.get_all(
		"Shaft Production Run",
		filters={"docstatus": 0, "modified": [">=", "2026-09-01"]},
		pluck="name",
		order_by="modified desc",
		limit_page_length=80,
	) or []
	recent_sub = frappe.get_all(
		"Shaft Production Run",
		filters={"docstatus": 1, "modified": [">=", "2026-09-01"]},
		pluck="name",
		order_by="modified desc",
		limit_page_length=40,
	) or []
	for n in recent_draft + recent_sub:
		if n not in names:
			names.append(n)

	for name in names:
		if not frappe.db.exists("Shaft Production Run", name):
			continue
		try:
			res = force_recalculate_spr_wastage_and_recycle(name)
			frappe.db.commit()
			frappe.logger("production_entry").info(f"force_recalc_v4 {name}: {res}")
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"force_recalculate_spr_wastage_v4:{name}")
