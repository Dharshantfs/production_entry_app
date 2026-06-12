# -*- coding: utf-8 -*-
"""Push 232-chain Parent Fabric Select options (232 RM Bag, 231 Main/Loop Fabric)."""
import frappe

from production_entry.production_planning.parent_fabric_options import repair_planning_child_table_metadata


def execute():
	repair_planning_child_table_metadata()
	for dt in ("Planning Table", "Planning sheet Item"):
		try:
			frappe.clear_cache(doctype=dt)
		except Exception:
			pass
