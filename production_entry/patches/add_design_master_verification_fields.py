# -*- coding: utf-8 -*-
"""Add Design Master custom fields for design verification (idempotent)."""

import frappe


def _add_field(docdict):
	key = f"{docdict['dt']}-{docdict['fieldname']}"
	try:
		if frappe.db.exists("Custom Field", key):
			return
		frappe.get_doc({"doctype": "Custom Field", **docdict}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"design_verification_field_{docdict.get('fieldname')}")


def execute():
	dt = None
	for candidate in ("DESIGN MASTER", "Design Master", "Design master"):
		if frappe.db.exists("DocType", candidate):
			dt = candidate
			break
	if not dt:
		return

	meta = frappe.get_meta(dt)
	anchor = "design_image" if meta.has_field("design_image") else "design_name"
	fields = [
		{"label": "Bag Type", "fieldname": "bag_type", "fieldtype": "Select", "options": "Auto\nBox Bag\nD Cut", "insert_after": "design_name", "default": "Auto"},
		{"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "insert_after": "bag_type"},
		{"label": "File Name", "fieldname": "file_name", "fieldtype": "Data", "read_only": 1, "insert_after": anchor},
		{"label": "File Type", "fieldname": "file_type", "fieldtype": "Data", "default": "CDR & PDF", "insert_after": "file_name"},
		{"label": "CDR Version", "fieldname": "cdr_version", "fieldtype": "Data", "default": "25 VERSION", "insert_after": "file_type"},
		{"label": "Verification Section", "fieldname": "verification_section", "fieldtype": "Section Break", "insert_after": "cdr_version", "collapsible": 1},
		{"label": "Verification Score", "fieldname": "verification_score", "fieldtype": "Percent", "read_only": 1, "insert_after": "verification_section"},
		{"label": "Verification Status", "fieldname": "verification_status", "fieldtype": "Select", "options": "Approved\nReview\nRejected", "read_only": 1, "insert_after": "verification_score", "in_list_view": 1},
		{"label": "AI Remarks", "fieldname": "ai_remarks", "fieldtype": "Text Editor", "read_only": 1, "insert_after": "verification_status"},
		{"label": "Width (mm)", "fieldname": "width", "fieldtype": "Float", "read_only": 1, "insert_after": "ai_remarks"},
		{"label": "Height (mm)", "fieldname": "height", "fieldtype": "Float", "read_only": 1, "insert_after": "width"},
		{"label": "Gusset (mm)", "fieldname": "gusset", "fieldtype": "Float", "read_only": 1, "insert_after": "height"},
		{"label": "Top Folding (mm)", "fieldname": "top_folding", "fieldtype": "Float", "read_only": 1, "insert_after": "gusset"},
		{"label": "Bag Size (inches)", "fieldname": "bag_size_inches", "fieldtype": "Data", "read_only": 1, "insert_after": "top_folding"},
		{"label": "PDF Page Preview", "fieldname": "pdf_page_preview", "fieldtype": "Attach Image", "read_only": 1, "insert_after": "bag_size_inches"},
		{"label": "Dominant Colors", "fieldname": "dominant_colors", "fieldtype": "Small Text", "read_only": 1, "insert_after": "pdf_page_preview"},
		{"label": "Last Verified On", "fieldname": "last_verified_on", "fieldtype": "Datetime", "read_only": 1, "insert_after": "dominant_colors"},
		{"label": "Checklist View (Excel Format)", "fieldname": "checklist_view_section", "fieldtype": "Section Break", "insert_after": "last_verified_on"},
		{"label": "Checklist View HTML", "fieldname": "checklist_view_html", "fieldtype": "HTML Editor", "read_only": 1, "insert_after": "checklist_view_section"},
		{"label": "Design Verification Checklist", "fieldname": "design_verification_checklist", "fieldtype": "Table", "options": "Design Verification Checklist", "insert_after": "checklist_view_html"},
		{"label": "Sign-off Section", "fieldname": "signoff_section", "fieldtype": "Section Break", "insert_after": "design_verification_checklist"},
		{"label": "Checked By Name", "fieldname": "checked_by_name", "fieldtype": "Data", "read_only": 1, "insert_after": "signoff_section"},
		{"label": "Checked By Date", "fieldname": "checked_by_date", "fieldtype": "Date", "read_only": 1, "insert_after": "checked_by_name"},
		{"label": "Checked By Sign", "fieldname": "checked_by_sign", "fieldtype": "Data", "insert_after": "checked_by_date"},
		{"label": "Extracted PDF Text", "fieldname": "extracted_pdf_text", "fieldtype": "Long Text", "read_only": 1, "insert_after": "checked_by_sign", "hidden": 1},
	]

	for f in fields:
		docdict = {"dt": dt, **f}
		_add_field(docdict)

	frappe.clear_cache(doctype=dt)
