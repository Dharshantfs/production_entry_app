# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe


def run_design_verification(doc, method=None):
	"""Run PDF verification on Design Master save/update."""
	if getattr(frappe.flags, "in_design_verification", False):
		return

	if doc.doctype != "Design Master" and not frappe.db.exists("DocType", "Design Master"):
		return

	image_field = _get_image_field(doc)
	if not image_field:
		return

	if not _should_run(doc, image_field):
		return

	file_url = getattr(doc, image_field, None)
	if not file_url or not _is_pdf_url(file_url):
		return

	try:
		frappe.flags.in_design_verification = True
		from production_entry.production_planning.design_verification.verification_engine import (
			verify_design,
		)

		verify_design(doc, file_url=file_url, image_field=image_field)

		# on_update: persist results without triggering another full save loop
		if method == "on_update" and doc.name and not doc.get("__islocal"):
			_persist_verification(doc)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Design Verification Error")
		if doc.meta.has_field("verification_status"):
			doc.verification_status = "Review"
		if doc.meta.has_field("ai_remarks"):
			doc.ai_remarks = (
				"Verification error — check Error Log (Design Verification Error). "
				"Common causes: migrate not run, pymupdf not installed, or PDF file not found."
			)
		if method == "on_update" and doc.name:
			_persist_verification(doc)
	finally:
		frappe.flags.in_design_verification = False


def _get_image_field(doc):
	for fn in ("design_image", "design_attachment", "custom_design_image", "custom_design_attachment"):
		if doc.meta.has_field(fn):
			return fn
	return None


def _is_pdf_url(file_url: str) -> bool:
	url = (file_url or "").lower().split("?")[0]
	return url.endswith(".pdf") or ".pdf" in url


def _should_run(doc, image_field: str) -> bool:
	file_url = getattr(doc, image_field, None)
	if not file_url or not _is_pdf_url(file_url):
		return False

	if doc.has_value_changed(image_field):
		return True

	# First-time verification or previous run produced nothing
	if not getattr(doc, "last_verified_on", None):
		return True

	if not (getattr(doc, "checklist_view_html", None) or "").strip():
		return True

	score = getattr(doc, "verification_score", None)
	if score in (None, "", 0, 0.0):
		return True

	return False


def _persist_verification(doc):
	"""Write verification output after on_update without re-entering hooks."""
	fields = {}
	for fn in (
		"width", "height", "gusset", "top_folding", "file_name", "file_type", "cdr_version",
		"pdf_page_preview", "dominant_colors", "extracted_pdf_text", "verification_score",
		"verification_status", "ai_remarks", "checklist_view_html", "last_verified_on",
		"checked_by_name", "checked_by_date",
	):
		if doc.meta.has_field(fn):
			fields[fn] = doc.get(fn)

	if fields:
		frappe.db.set_value("Design Master", doc.name, fields, update_modified=False)

	# Replace child table rows
	if doc.meta.has_field("design_verification_checklist"):
		frappe.db.delete("Design Verification Checklist", {"parent": doc.name})
		for row in doc.get("design_verification_checklist") or []:
			row.parent = doc.name
			row.parenttype = "Design Master"
			row.parentfield = "design_verification_checklist"
			row.db_insert()


@frappe.whitelist()
def run_verification_now(design_master: str):
	"""Manual re-run from desk (browser console or custom button)."""
	doc = frappe.get_doc("Design Master", design_master)
	frappe.flags.in_design_verification = False
	run_design_verification(doc, method="on_update")
	return {
		"verification_score": doc.get("verification_score"),
		"verification_status": doc.get("verification_status"),
		"ai_remarks": doc.get("ai_remarks"),
	}
