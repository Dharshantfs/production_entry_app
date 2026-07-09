# -*- coding: utf-8 -*-
"""Widen planning transfer status/destination columns for long company labels."""

import frappe


def execute():
	fields = ("custom_transfer_destination", "custom_transfer_status")
	for dt in ("Planning Table", "Planning sheet Item"):
		if not frappe.db.table_exists(dt):
			continue
		for field in fields:
			if not frappe.db.has_column(dt, field):
				continue
			try:
				frappe.db.sql(
					f"ALTER TABLE `tab{dt}` MODIFY COLUMN `{field}` VARCHAR(500)"
				)
			except Exception:
				frappe.log_error(
					frappe.get_traceback(),
					f"expand_transfer_destination_column_length:{dt}.{field}",
				)
	frappe.db.commit()
