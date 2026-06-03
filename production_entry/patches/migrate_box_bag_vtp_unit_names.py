# -*- coding: utf-8 -*-
"""Rename box-bag L1/L2 workstation labels to VTP-L1 / VTP-L2 (removes duplicate machines)."""

import frappe

from production_entry.production_planning.planning_doctypes import (
	BOX_BAG_UNIT_L1,
	BOX_BAG_UNIT_L2,
	LEGACY_BOX_BAG_UNIT_L1,
	LEGACY_BOX_BAG_UNIT_L2,
	ensure_planning_workstation_record,
)

_RENAMES = (
	(LEGACY_BOX_BAG_UNIT_L1, BOX_BAG_UNIT_L1),
	(LEGACY_BOX_BAG_UNIT_L2, BOX_BAG_UNIT_L2),
)

_UNIT_TABLES = (
	"tabPlanning Table",
	"tabPlanning sheet Item",
)


def _rename_workstation(old: str, new: str):
	if not old or old == new:
		return
	if not frappe.db.exists("Workstation", old):
		return
	if frappe.db.exists("Workstation", new):
		try:
			frappe.delete_doc("Workstation", old, force=1, ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"migrate_box_bag_ws_delete:{old}")
		return
	try:
		frappe.rename_doc("Workstation", old, new, force=True, merge=False)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"migrate_box_bag_ws_rename:{old}->{new}")


def execute():
	for old, new in _RENAMES:
		for table in _UNIT_TABLES:
			try:
				frappe.db.sql(
					f"UPDATE `{table}` SET `unit`=%s WHERE `unit`=%s",
					(new, old),
				)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"migrate_box_bag_unit:{table}:{old}")
		if frappe.db.has_column("Shaft Production Run", "custom_unit"):
			try:
				frappe.db.sql(
					"UPDATE `tabShaft Production Run` SET `custom_unit`=%s WHERE `custom_unit`=%s",
					(new, old),
				)
			except Exception:
				frappe.log_error(frappe.get_traceback(), "migrate_box_bag_unit:SPR")
		_rename_workstation(old, new)

	for ws_name in (BOX_BAG_UNIT_L1, BOX_BAG_UNIT_L2):
		ensure_planning_workstation_record(ws_name)

	frappe.db.commit()
