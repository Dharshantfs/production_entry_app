# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe


def run_design_verification(doc, method=None):
	if getattr(frappe.flags, "in_design_verification", False):
		return

	if not frappe.db.exists("DocType", "Design Master"):
		return

	image_field = None
	for fn in ("design_image", "design_attachment"):
		if doc.meta.has_field(fn):
			image_field = fn
			break
	if not image_field:
		return

	if not doc.has_value_changed(image_field):
		return

	file_url = getattr(doc, image_field, None)
	if not file_url or not str(file_url).lower().endswith(".pdf"):
		return

	try:
		frappe.flags.in_design_verification = True
		from production_entry.production_planning.design_verification.verification_engine import verify_design

		verify_design(doc)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Design Verification Error")
		if doc.meta.has_field("verification_status"):
			doc.verification_status = "Review"
		if doc.meta.has_field("ai_remarks"):
			doc.ai_remarks = "Verification encountered an error. Please review manually."
	finally:
		frappe.flags.in_design_verification = False
