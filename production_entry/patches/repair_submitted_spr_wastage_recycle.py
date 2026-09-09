# -*- coding: utf-8 -*-
"""Repair submitted SPRs where Running Patty Wastage qty became 0 and Recycled table is empty.

Runs after the GSM Recycle-to-Next alias fix so meter/shafts/qty and recycle rows are restored
from shaft jobs / roll lines without amending the parent document.
"""
from __future__ import annotations

import frappe


def execute():
	from production_entry.production_planning.doctype.shaft_production_run.shaft_production_run import (
		_spr_submitted_needs_wastage_repair,
		persist_spr_patty_and_core,
	)

	names = frappe.get_all(
		"Shaft Production Run",
		filters={"docstatus": 1},
		pluck="name",
		order_by="modified desc",
		limit_page_length=300,
	) or []

	# Always include known broken docs from the GSM wastage-zero incident
	for known in ("SPR-2026-00802", "SPR-2026-00803", "SPR-2026-00799"):
		if frappe.db.exists("Shaft Production Run", known):
			names.append(known)

	seen = set()
	for name in names:
		if name in seen:
			continue
		seen.add(name)
		try:
			if not _spr_submitted_needs_wastage_repair(name):
				continue
			persist_spr_patty_and_core(
				name,
				only_if_empty=False,
				save_if_draft=False,
				refresh_zero_rows=True,
			)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"repair_submitted_spr_wastage_recycle:{name}")
