# -*- coding: utf-8 -*-
"""Rename legacy Select ``unit`` values to Workstation names (``unit`` → Link Workstation).

Idempotent: only rows whose value still equals an old label are updated. Safe for large datasets.
"""

import frappe

from production_entry.production_planning.planning_doctypes import (
	LAMINATION_UNIT,
	REWINDING_UNASSIGNED_UNIT,
	SLITTING_UNIT,
)

_REPLACEMENTS = (
	("Lamination Unit", LAMINATION_UNIT),
	("Slitting Unit", SLITTING_UNIT),
	("Unassigned rewinding machine", REWINDING_UNASSIGNED_UNIT),
	("Mixed", "UNASSIGNED"),
	("UNIT 1", "Unit 1"),
	("UNIT 2", "Unit 2"),
	("UNIT 3", "Unit 3"),
	("UNIT 4", "Unit 4"),
)

_UNIT_TABLES = (
	"tabPlanning Table",
	"tabPlanning sheet Item",
	"tabEquipment Maintenance",
	"tabColor Sequence Approval",
)


def _swap(table: str, field: str):
	for old, new in _REPLACEMENTS:
		if not old or old == new:
			continue
		frappe.db.sql(
			f"UPDATE `{table}` SET `{field}`=%s WHERE `{field}`=%s",
			(new, old),
		)


def execute():
	for t in _UNIT_TABLES:
		try:
			_swap(t, "unit")
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"migrate_planning_units:{t}")

	if frappe.db.has_column("Shaft Production Run", "custom_unit"):
		try:
			_swap("tabShaft Production Run", "custom_unit")
		except Exception:
			frappe.log_error(frappe.get_traceback(), "migrate_planning_units:Shaft Production Run")

	frappe.db.commit()
