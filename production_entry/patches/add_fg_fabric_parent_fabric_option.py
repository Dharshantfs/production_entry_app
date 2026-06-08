# -*- coding: utf-8 -*-
"""Re-sync Parent Fabric Select options (includes FG Fabric)."""
import frappe

from production_entry.production_planning.parent_fabric_options import PARENT_FABRIC_OPTIONS


def execute():
	for dt in ("Planning Table", "Planning sheet Item"):
		cf_name = frappe.db.get_value(
			"Custom Field",
			{"dt": dt, "fieldname": "custom_parent_fabric"},
			"name",
		)
		if cf_name:
			frappe.db.set_value("Custom Field", cf_name, "options", PARENT_FABRIC_OPTIONS, update_modified=False)
	frappe.db.commit()
