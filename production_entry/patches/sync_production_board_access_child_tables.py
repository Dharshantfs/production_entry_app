# -*- coding: utf-8 -*-
"""Deprecated — do not force-reload board access DocTypes (preserves manual site setup)."""
import frappe


def execute():
	frappe.log_error(
		"Skipped sync_production_board_access_child_tables (use install._ensure_board_access_child_doctypes_if_missing)",
		"sync_production_board_access_child_tables",
	)
