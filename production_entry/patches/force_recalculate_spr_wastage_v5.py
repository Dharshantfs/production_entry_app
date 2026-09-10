# -*- coding: utf-8 -*-
"""v5: refill Running Patty rows the desk Client Script had saved with zeros."""
from __future__ import annotations

import frappe


def execute():
	from production_entry.production_planning.doctype.shaft_production_run.shaft_production_run import (
		force_recalculate_spr_wastage_and_recycle,
	)

	names = []
	for docstatus, limit in ((0, 120), (1, 60)):
		names.extend(
			frappe.get_all(
				"Shaft Production Run",
				filters={"docstatus": docstatus, "modified": [">=", "2026-09-01"]},
				pluck="name",
				order_by="modified desc",
				limit_page_length=limit,
			)
			or []
		)

	for name in dict.fromkeys(names):
		try:
			force_recalculate_spr_wastage_and_recycle(name)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"force_recalculate_spr_wastage_v5:{name}")
