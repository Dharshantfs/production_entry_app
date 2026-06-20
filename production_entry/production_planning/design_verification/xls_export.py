# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import io

import frappe

from production_entry.production_planning.design_verification.doctype_utils import get_design_master_doctype


@frappe.whitelist()
def download_design_checklist_xlsx(design_master: str, doctype: str | None = None):
	dt = doctype or get_design_master_doctype()
	if not dt:
		frappe.throw("Design Master DocType not found on this site.")
	doc = frappe.get_doc(dt, design_master)
	try:
		from openpyxl import Workbook
		from openpyxl.styles import Font
	except ImportError:
		frappe.throw("openpyxl is not installed")

	wb = Workbook()
	ws = wb.active
	ws.title = "Checklist"
	bold = Font(bold=True)
	ws.append([
		f"DESIGN NAME: {doc.design_name or ''}",
		f"FILE NAME: {doc.file_name or ''}",
		f"FILE TYPE: {doc.file_type or 'CDR & PDF'}",
		f"CDR VERSION: {doc.cdr_version or '25 VERSION'}",
	])
	ws.append([])
	ws.append(["S.No", "Particulars", "", "", "Measurement", "Checklist"],)

	prev_key = None
	for row in doc.design_verification_checklist or []:
		key = (row.sno, row.particulars)
		ws.append([
			row.sno if key != prev_key else "",
			row.particulars if key != prev_key else "",
			row.sub_item or "",
			row.sub_particular or "",
			row.measurement or "",
			row.checklist or "0",
		])
		prev_key = key

	ws.append([])
	ws.append(["CHECKED BY"])
	ws.append([f"NAME : {doc.checked_by_name or ''}"])
	ws.append([f"DATE : {doc.checked_by_date or ''}"])
	ws.append([f"SIGN: {doc.checked_by_sign or ''}"])

	buf = io.BytesIO()
	wb.save(buf)
	buf.seek(0)
	frappe.local.response.filename = f"{frappe.scrub(doc.name)}_checklist.xlsx"
	frappe.local.response.filecontent = buf.read()
	frappe.local.response.type = "download"
