# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe

from production_entry.production_planning.design_verification.doctype_utils import (
	get_design_master_doctype,
	is_design_master_doc,
)


def _mark_manual_checklist_edits(doc) -> None:
	if doc.get("__islocal") or not doc.name:
		return
	if not doc.meta.has_field("design_verification_checklist"):
		return
	try:
		old = frappe.get_doc(doc.doctype, doc.name)
	except Exception:
		return

	old_map = {}
	for row in old.get("design_verification_checklist") or []:
		key = (row.particulars or "", row.sub_item or "", row.sub_particular or "")
		old_map[key] = row

	for row in doc.get("design_verification_checklist") or []:
		key = (row.particulars or "", row.sub_item or "", row.sub_particular or "")
		old_row = old_map.get(key)
		if not old_row:
			continue
		if (
			(row.checklist or "") != (old_row.checklist or "")
			or (row.measurement or "") != (old_row.measurement or "")
			or (row.remarks or "") != (old_row.remarks or "")
		):
			row.manually_edited = 1


def run_design_verification(doc, method=None):
	"""Run PDF verification on Design Master save/update."""
	if getattr(frappe.flags, "in_design_verification", False):
		return

	if not is_design_master_doc(doc):
		return

	image_field = _get_image_field(doc)
	if not image_field:
		return

	file_url = getattr(doc, image_field, None)
	if not file_url or not _is_pdf_url(file_url):
		return

	try:
		frappe.flags.in_design_verification = True
		_mark_manual_checklist_edits(doc)
		from production_entry.production_planning.design_verification.verification_engine import (
			recalculate_score_from_checklist,
			verify_design,
		)

		pdf_changed = doc.has_value_changed(image_field)
		has_checklist = bool(doc.get("design_verification_checklist"))
		has_manual = _has_manual_edits(doc)
		force = bool(getattr(frappe.flags, "force_design_verification", False))

		if pdf_changed or force or not has_checklist:
			verify_design(doc, file_url=file_url, image_field=image_field, replace_checklist=True)
		elif has_manual or has_checklist:
			recalculate_score_from_checklist(doc, manual_override=True)
		elif _should_run(doc, image_field):
			verify_design(doc, file_url=file_url, image_field=image_field, replace_checklist=True)

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


def _has_manual_edits(doc) -> bool:
	for row in doc.get("design_verification_checklist") or []:
		if getattr(row, "manually_edited", 0):
			return True
	return False


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

	if not getattr(doc, "last_verified_on", None):
		return True

	if not (getattr(doc, "checklist_view_html", None) or "").strip():
		return True

	score = getattr(doc, "verification_score", None)
	if score in (None, "", 0, 0.0):
		return True

	return False


def _persist_verification(doc):
	fields = {}
	for fn in (
		"width", "height", "gusset", "top_folding", "bag_size_inches", "file_name", "file_type", "cdr_version",
		"pdf_page_preview", "dominant_colors", "extracted_pdf_text", "verification_score",
		"verification_status", "ai_remarks", "checklist_view_html", "last_verified_on",
		"checked_by_name", "checked_by_date",
	):
		if doc.meta.has_field(fn):
			fields[fn] = doc.get(fn)

	if fields:
		frappe.db.set_value(doc.doctype, doc.name, fields, update_modified=False)

	if doc.meta.has_field("design_verification_checklist"):
		frappe.db.delete("Design Verification Checklist", {"parent": doc.name})
		for row in doc.get("design_verification_checklist") or []:
			row.parent = doc.name
			row.parenttype = doc.doctype
			row.parentfield = "design_verification_checklist"
			row.db_insert()


@frappe.whitelist()
def run_verification_now(design_master: str, doctype: str | None = None, force: int | str = 0):
	"""Manual re-run from desk. Pass force=1 to replace checklist even if manually edited."""
	dt = doctype or get_design_master_doctype()
	if not dt:
		frappe.throw("Design Master DocType not found on this site.")

	from production_entry.production_planning.design_verification.verification_engine import (
		_resolve_design_master_name,
	)

	doc_name = _resolve_design_master_name(dt, design_master)
	if not doc_name:
		frappe.throw(
			f"Document {design_master} not found in {dt}. "
			"Use the document name or design_code (e.g. 6126)."
		)

	doc = frappe.get_doc(dt, doc_name)
	frappe.flags.in_design_verification = False
	frappe.flags.force_design_verification = bool(int(force or 0))
	run_design_verification(doc, method="on_update")
	frappe.flags.force_design_verification = False
	return {
		"verification_score": doc.get("verification_score"),
		"verification_status": doc.get("verification_status"),
		"ai_remarks": doc.get("ai_remarks"),
		"doctype": dt,
	}
