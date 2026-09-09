# -*- coding: utf-8 -*-
"""v2: force-repair submitted SPRs still stuck with wastage qty=0 / empty recycle after first patch."""
from __future__ import annotations

import frappe


def execute():
	from production_entry.production_planning.doctype.shaft_production_run.shaft_production_run import (
		persist_spr_patty_and_core,
	)

	names = [
		"SPR-2026-00809",
		"SPR-2026-00802",
		"SPR-2026-00803",
		"SPR-2026-00799",
	]
	# Plus any other recent submitted Unit SPRs with zero wastage rows
	recent = frappe.get_all(
		"Shaft Production Run",
		filters={"docstatus": 1, "modified": [">=", "2026-09-01"]},
		pluck="name",
		order_by="modified desc",
		limit_page_length=80,
	) or []
	for n in recent:
		if n not in names:
			names.append(n)

	for name in names:
		if not frappe.db.exists("Shaft Production Run", name):
			continue
		try:
			res = persist_spr_patty_and_core(
				name,
				only_if_empty=False,
				save_if_draft=False,
				refresh_zero_rows=True,
			)
			frappe.db.commit()
			frappe.logger("production_entry").info(f"repair_v2 {name}: {res}")
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"repair_submitted_spr_wastage_recycle_v2:{name}")
