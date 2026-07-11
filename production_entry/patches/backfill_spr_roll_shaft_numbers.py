"""One-time backfill: fix custom_no_of_shaft=0 on draft Shaft Production Run roll lines."""

from __future__ import annotations

import frappe

from production_entry.production_planning.doctype.shaft_production_run.shaft_production_run import (
	_backfill_spr_roll_shaft_numbers_for_doc,
)


def execute():
	if not frappe.db.table_exists("Shaft Production Run"):
		return
	if not frappe.db.has_column("Shaft Production Run Item", "custom_no_of_shaft"):
		return

	names = frappe.get_all(
		"Shaft Production Run",
		filters={"docstatus": 0},
		pluck="name",
		limit=500,
	)
	total_rows = 0
	total_sprs = 0
	for name in names or []:
		spr = frappe.get_doc("Shaft Production Run", name)
		result = _backfill_spr_roll_shaft_numbers_for_doc(spr, save=True)
		fixed = cint(result.get("rows_fixed") or 0)
		if fixed:
			total_rows += fixed
			total_sprs += 1

	if total_rows:
		frappe.logger("production_entry").info(
			"backfill_spr_roll_shaft_numbers: fixed %s row(s) across %s draft SPR(s)",
			total_rows,
			total_sprs,
		)


def cint(val):
	from frappe.utils import cint as _cint

	return _cint(val)
