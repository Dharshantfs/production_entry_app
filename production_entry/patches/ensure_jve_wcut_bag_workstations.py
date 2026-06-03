# -*- coding: utf-8 -*-
"""Ensure JVE B700 bag making Workstation records exist (W/CUT–D/CUT board)."""

from production_entry.production_planning.planning_doctypes import (
	W_CUT_D_CUT_UNIT_JVE_L1,
	W_CUT_D_CUT_UNIT_JVE_L2,
	W_CUT_D_CUT_UNIT_JVE_L3,
)


def execute():
	import frappe

	for name in (W_CUT_D_CUT_UNIT_JVE_L1, W_CUT_D_CUT_UNIT_JVE_L2, W_CUT_D_CUT_UNIT_JVE_L3):
		if frappe.db.exists("Workstation", name):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Workstation",
				"workstation_name": name,
				"workstation_type": "Bag Making",
			}
		)
		doc.insert(ignore_permissions=True)
	frappe.db.commit()
