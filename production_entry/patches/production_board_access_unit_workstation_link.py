# -*- coding: utf-8 -*-
"""Deprecated — do not force-reload board access DocTypes (preserves manual site setup)."""
import frappe


def execute():
	frappe.log_error(
		"Skipped production_board_access_unit_workstation_link (manual/custom child DocTypes are preserved)",
		"production_board_access_unit_workstation_link",
	)
