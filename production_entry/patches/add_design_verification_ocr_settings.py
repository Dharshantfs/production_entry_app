# -*- coding: utf-8 -*-
"""Add OCR settings fields to Design Verification Settings."""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Design Verification Settings"):
		return
	frappe.reload_doc("Production Planning", "doctype", "design_verification_settings")
	settings = frappe.get_single("Design Verification Settings")
	if getattr(settings, "ocr_enabled", None) is None:
		settings.ocr_enabled = 1
	if not getattr(settings, "ocr_dpi", None):
		settings.ocr_dpi = 300
	settings.save(ignore_permissions=True)
