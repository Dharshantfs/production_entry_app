# -*- coding: utf-8 -*-
"""Ensure Production Board Access child DocTypes have importable Python controllers."""
import frappe


_CHILD = (
	"production_board_access_unit",
	"production_board_access_board",
	"production_board_access_color_chart",
	"production_board_access_gsm",
)


def execute():
	for folder in _CHILD:
		try:
			frappe.reload_doc("production_planning", "doctype", folder)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"sync_production_board_access_child_controllers: {folder}")
	frappe.clear_cache()
