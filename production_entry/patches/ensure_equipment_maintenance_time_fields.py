"""Ensure Equipment Maintenance has start_time / end_time for partial-day capacity."""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Equipment Maintenance"):
		return

	from production_entry.production_planning.scheduler_api import (
		_ensure_equipment_maintenance_time_fields,
	)

	_ensure_equipment_maintenance_time_fields()
