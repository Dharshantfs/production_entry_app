# -*- coding: utf-8 -*-
"""Ensure JVE B700 bag making Workstation records exist (W/CUT–D/CUT board)."""

from production_entry.production_planning.planning_doctypes import (
	W_CUT_D_CUT_UNIT_JVE_L1,
	W_CUT_D_CUT_UNIT_JVE_L2,
	W_CUT_D_CUT_UNIT_JVE_L3,
)


def execute():
	from production_entry.production_planning.planning_doctypes import ensure_planning_workstation_record

	for name in (W_CUT_D_CUT_UNIT_JVE_L1, W_CUT_D_CUT_UNIT_JVE_L2, W_CUT_D_CUT_UNIT_JVE_L3):
		ensure_planning_workstation_record(name)
	frappe.db.commit()
