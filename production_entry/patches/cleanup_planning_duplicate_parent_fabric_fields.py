# -*- coding: utf-8 -*-
"""Remove duplicate Parent Fabric Custom Fields; make Work Order editable on both planning grids."""
import frappe

from production_entry.production_planning.parent_fabric_options import repair_planning_child_table_metadata


def execute():
	repair_planning_child_table_metadata()

	try:
		from production_entry.production_planning.scheduler_api import (
			_sync_planning_board_work_orders_from_items,
		)

		for ps_name in frappe.get_all("Planning sheet", pluck="name") or []:
			try:
				_sync_planning_board_work_orders_from_items(ps_name)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"backfill_board_wo:{ps_name}")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "cleanup_parent_fabric:wo_backfill")

	frappe.db.commit()
