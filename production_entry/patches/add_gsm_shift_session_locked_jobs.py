"""Add GSM Shift Session locked job selection fields (selection_locked + locked_jobs child table)."""

from __future__ import annotations

import frappe


def execute():
	if not frappe.db.table_exists("GSM Shift Session"):
		return
	frappe.reload_doc("production_planning", "doctype", "gsm_shift_session_job")
	frappe.reload_doc("production_planning", "doctype", "gsm_shift_session")
