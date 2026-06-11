# -*- coding: utf-8 -*-
"""Push 232-chain Parent Fabric Select options (232 RM Bag, 231 Main/Loop Fabric)."""
import frappe

from production_entry.production_planning.parent_fabric_options import sync_parent_fabric_field_options_to_db


def execute():
	sync_parent_fabric_field_options_to_db()
	for dt in ("Planning Table", "Planning sheet Item"):
		try:
			frappe.clear_cache(doctype=dt)
		except Exception:
			pass
