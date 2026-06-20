# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
import os
import types

import frappe

from production_entry.production_planning.design_verification.ai_remarks import generate_ai_remarks
from production_entry.production_planning.design_verification.checklist_renderer import render_checklist_html
from production_entry.production_planning.design_verification.constants import (
	DEFAULT_GOV_PHRASES,
	DEFAULT_LOGO_PHRASES,
	get_all_default_rules,
)
from production_entry.production_planning.design_verification import image_utils
from production_entry.production_planning.design_verification.pdf_utils import analyze_pdf, save_preview_to_design
from production_entry.production_planning.design_verification.rule_runner import run_rule
from production_entry.production_planning.design_verification.spatial_engine import build_spatial_context


class _FallbackSettings:
	"""Used when Design Verification Settings singleton is missing or disabled."""

	enabled = 1
	customer_field_source = "Design Name"
	approved_threshold = 90
	review_threshold = 70
	mm_tolerance = 2.0
	check_rules = []
	logo_phrases = []
	mandatory_government_text = []


def _get_settings():
	try:
		if frappe.db.exists("DocType", "Design Verification Settings"):
			settings = frappe.get_single("Design Verification Settings")
			if settings.enabled:
				if settings.check_rules:
					return settings
				return _build_settings_from_defaults(settings)
			# disabled — still allow run with defaults if explicitly triggered
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Design Verification Settings Load")
	return _build_settings_from_defaults(None)


def _build_settings_from_defaults(existing):
	settings = existing or _FallbackSettings()
	if not getattr(settings, "check_rules", None):
		settings.check_rules = []
		for rule in get_all_default_rules():
			settings.check_rules.append(types.SimpleNamespace(**{
				"bag_type": rule["bag_type"],
				"sno": rule["sno"],
				"particulars": rule["particulars"],
				"sub_item": rule["sub_item"],
				"sub_particular": rule["sub_particular"],
				"check_item": rule["check_item"],
				"expected_measurement": rule["expected_measurement"],
				"check_method": rule["check_method"],
				"rule_config": rule["rule_config"],
				"required_for_score": rule["required_for_score"],
				"sort_order": rule["sort_order"],
			}))
	if not getattr(settings, "logo_phrases", None):
		settings.logo_phrases = [types.SimpleNamespace(phrase=p) for p in DEFAULT_LOGO_PHRASES]
	if not getattr(settings, "mandatory_government_text", None):
		settings.mandatory_government_text = [
			types.SimpleNamespace(phrase=r["phrase"], required=r["required"]) for r in DEFAULT_GOV_PHRASES
		]
	settings.approved_threshold = getattr(settings, "approved_threshold", None) or 90
	settings.review_threshold = getattr(settings, "review_threshold", None) or 70
	settings.mm_tolerance = getattr(settings, "mm_tolerance", None) or 2.0
	return settings


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
		bt = getattr(rule, "bag_type", None) or "Both"
		if bt == "Both" or bt == bag_type:
			out.append(rule)
	out.sort(key=lambda r: (getattr(r, "sno", 0) or 0, getattr(r, "sort_order", 0) or 0))
	return out


def _rule_config(rule):
	cfg = getattr(rule, "rule_config", None)
	if isinstance(cfg, str):
		try:
			return json.loads(cfg) if cfg else {}
		except Exception:
			return {}
	return cfg or {}


def verify_design(doc, file_url: str | None = None, image_field: str | None = None) -> None:
	settings = _get_settings()

	if not file_url:
		for fn in ("design_image", "design_attachment", "custom_design_image"):
			file_url = getattr(doc, fn, None)
			if file_url:
				image_field = fn
				break

	if not file_url:
		if doc.meta.has_field("ai_remarks"):
			doc.ai_remarks = "No PDF attached in design_image field."
		return

	analysis = analyze_pdf(file_url)
	if not analysis.file_path:
		msg = (
			f"Could not read PDF at {file_url}. "
			"Ensure file is saved and pymupdf is installed on the server."
		)
		if doc.meta.has_field("ai_remarks"):
			doc.ai_remarks = msg
		frappe.log_error(msg, "Design Verification PDF Path")
		return

	bag_type = _detect_bag_type(doc, analysis, getattr(doc, "bag_type", None))
	spatial = build_spatial_context(analysis, float(settings.mm_tolerance or 2.0))

	qr_ok, qr_msg = image_utils.detect_qr(analysis.rendered_image_path)
	colors = image_utils.detect_dominant_colors(analysis.rendered_image_path)

	doc.width = analysis.width or 0
	doc.height = analysis.height or 0
	doc.gusset = analysis.gusset or 0
	doc.top_folding = analysis.top_folding or 0
	doc.file_name = _filename_from_url(file_url)
	if doc.meta.has_field("file_type") and not doc.get("file_type"):
		doc.file_type = "CDR & PDF"
	if doc.meta.has_field("cdr_version") and not doc.get("cdr_version"):
		doc.cdr_version = "25 VERSION"

	preview_url = save_preview_to_design(doc, analysis.rendered_image_path, doc.get("design_name"))
	if preview_url and doc.meta.has_field("pdf_page_preview"):
		doc.pdf_page_preview = preview_url
	if colors and doc.meta.has_field("dominant_colors"):
		doc.dominant_colors = ", ".join(colors)
	if doc.meta.has_field("extracted_pdf_text"):
		doc.extracted_pdf_text = (analysis.full_text or "")[:65000]

	rules = _filter_rules(settings, bag_type)
	if not rules:
		if doc.meta.has_field("ai_remarks"):
			doc.ai_remarks = "No verification rules loaded. Run bench migrate on the site."
		return

	checklist_rows = []
	scored = 0
	passed_count = 0
	seen_groups = set()

	for rule in rules:
		# attach parsed config for rule_runner
		rule.rule_config = _rule_config(rule)
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
		if getattr(rule, "required_for_score", 1):
			scored += 1
			if row["result"] == "Pass":
				passed_count += 1

	score = (passed_count / scored * 100) if scored else 0
	approved = int(settings.approved_threshold or 90)
	review = int(settings.review_threshold or 70)
	if scored == 0:
		status = "Review"
	elif score >= approved:
		status = "Approved"
	elif score >= review:
		status = "Review"
	else:
		status = "Rejected"

	if doc.meta.has_field("verification_score"):
		doc.verification_score = score
	if doc.meta.has_field("verification_status"):
		doc.verification_status = status

	if doc.meta.has_field("design_verification_checklist"):
		doc.set("design_verification_checklist", [])
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
		for i, row in enumerate(checklist_rows):
			if i < len(doc.design_verification_checklist):
				child = doc.design_verification_checklist[i]
				child.sno = row["sno"]
				child.particulars = row["particulars"]

	if doc.meta.has_field("ai_remarks"):
		doc.ai_remarks = generate_ai_remarks(doc, bag_type, checklist_rows, score, status)
	if doc.meta.has_field("checklist_view_html"):
		doc.checklist_view_html = render_checklist_html(doc)
	if doc.meta.has_field("last_verified_on"):
		doc.last_verified_on = frappe.utils.now_datetime()
	if doc.meta.has_field("checked_by_name"):
		doc.checked_by_name = frappe.utils.get_fullname(frappe.session.user)
	if doc.meta.has_field("checked_by_date"):
		doc.checked_by_date = frappe.utils.today()

	if analysis.rendered_image_path and os.path.isfile(analysis.rendered_image_path):
		try:
			os.remove(analysis.rendered_image_path)
		except OSError:
			pass
