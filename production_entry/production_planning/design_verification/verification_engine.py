# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import os
import re

import frappe

from production_entry.production_planning.design_verification.ai_remarks import generate_ai_remarks
from production_entry.production_planning.design_verification.checklist_renderer import render_checklist_html
from production_entry.production_planning.design_verification import image_utils, text_utils
from production_entry.production_planning.design_verification.pdf_utils import analyze_pdf, save_preview_to_design
from production_entry.production_planning.design_verification.rule_runner import run_rule
from production_entry.production_planning.design_verification.spatial_engine import build_spatial_context


def _get_settings():
	try:
		if frappe.db.exists("DocType", "Design Verification Settings"):
			return frappe.get_single("Design Verification Settings")
	except Exception:
		pass
	return None


def _detect_bag_type(doc, analysis, override: str | None) -> str:
	if override and override not in ("Auto", ""):
		return override
	if analysis.gusset:
		return "Box Bag"
	if analysis.width and analysis.height and not analysis.gusset:
		return "D Cut"
	return "Box Bag"


def _filename_from_url(file_url: str) -> str:
	if not file_url:
		return ""
	return os.path.basename(file_url.split("?")[0])


def _filter_rules(settings, bag_type: str):
	rules = list(settings.check_rules or [])
	out = []
	for rule in rules:
		bt = rule.bag_type or "Both"
		if bt == "Both" or bt == bag_type:
			out.append(rule)
	out.sort(key=lambda r: (r.sno or 0, r.sort_order or 0))
	return out


def verify_design(doc) -> None:
	settings = _get_settings()
	if not settings or not settings.enabled:
		return

	file_url = getattr(doc, "design_image", None) or getattr(doc, "design_attachment", None)
	if not file_url or not str(file_url).lower().endswith(".pdf"):
		return

	analysis = analyze_pdf(file_url)
	if not analysis.file_path:
		return

	bag_type = _detect_bag_type(doc, analysis, getattr(doc, "bag_type", None))
	spatial = build_spatial_context(analysis, float(settings.mm_tolerance or 2.0))

	qr_ok, qr_msg = image_utils.detect_qr(analysis.rendered_image_path)
	colors = image_utils.detect_dominant_colors(analysis.rendered_image_path)

	# populate dimensions on doc
	doc.width = analysis.width
	doc.height = analysis.height
	doc.gusset = analysis.gusset
	doc.top_folding = analysis.top_folding
	doc.file_name = _filename_from_url(file_url)
	if not getattr(doc, "file_type", None):
		doc.file_type = "CDR & PDF"
	if not getattr(doc, "cdr_version", None):
		doc.cdr_version = "25 VERSION"

	preview_url = save_preview_to_design(doc, analysis.rendered_image_path, doc.design_name)
	if preview_url:
		doc.pdf_page_preview = preview_url
	if colors:
		doc.dominant_colors = ", ".join(colors)
	doc.extracted_pdf_text = (analysis.full_text or "")[:65000]

	rules = _filter_rules(settings, bag_type)
	checklist_rows = []
	scored = 0
	passed_count = 0

	seen_groups = set()
	for rule in rules:
		outcome = run_rule(rule, doc, settings, analysis, spatial, qr_ok, qr_msg, colors)
		group_key = (rule.sno, rule.particulars)
		is_header = group_key not in seen_groups
		if is_header:
			seen_groups.add(group_key)

		row = {
			"sno": rule.sno,
			"particulars": rule.particulars,
			"sub_item": rule.sub_item,
			"sub_particular": rule.sub_particular,
			"measurement": outcome.get("measurement") or rule.expected_measurement or "",
			"checklist": outcome.get("checklist") or "0",
			"result": outcome.get("result") or "Fail",
			"remarks": outcome.get("remarks") or "",
			"check_method": outcome.get("check_method") or rule.check_method,
			"is_group_header": 1 if is_header else 0,
			"check_item": rule.check_item,
		}
		checklist_rows.append(row)
		if rule.required_for_score:
			scored += 1
			if row["result"] == "Pass":
				passed_count += 1

	score = (passed_count / scored * 100) if scored else 0
	approved = int(settings.approved_threshold or 90)
	review = int(settings.review_threshold or 70)
	if score >= approved:
		status = "Approved"
	elif score >= review:
		status = "Review"
	else:
		status = "Rejected"

	doc.verification_score = score
	doc.verification_status = status
	doc.design_verification_checklist = []
	for row in checklist_rows:
		doc.append("design_verification_checklist", {
			"sno": row["sno"] if row["is_group_header"] else None,
			"particulars": row["particulars"] if row["is_group_header"] else "",
			"sub_item": row["sub_item"],
			"sub_particular": row["sub_particular"],
			"measurement": row["measurement"],
			"checklist": row["checklist"],
			"result": row["result"],
			"remarks": row["remarks"],
			"check_method": row["check_method"],
			"is_group_header": row["is_group_header"],
		})

	# Restore grouping keys on child rows for renderer
	for i, row in enumerate(checklist_rows):
		child = doc.design_verification_checklist[i]
		child.sno = row["sno"]
		child.particulars = row["particulars"]

	doc.ai_remarks = generate_ai_remarks(doc, bag_type, checklist_rows, score, status)
	doc.checklist_view_html = render_checklist_html(doc)
	doc.last_verified_on = frappe.utils.now_datetime()
	doc.checked_by_name = frappe.utils.get_fullname(frappe.session.user)
	doc.checked_by_date = frappe.utils.today()

	# cleanup temp preview file
	if analysis.rendered_image_path and os.path.isfile(analysis.rendered_image_path):
		try:
			os.remove(analysis.rendered_image_path)
		except OSError:
			pass
