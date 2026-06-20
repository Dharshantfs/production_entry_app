# -*- coding: utf-8 -*-
"""Import Design Verification DocTypes and seed Settings with Box Bag / D Cut rules."""

import json
import os

import frappe
from frappe.modules.import_file import import_file_by_path

from production_entry.production_planning.design_verification.constants import (
	DEFAULT_GOV_PHRASES,
	DEFAULT_LOGO_PHRASES,
	get_all_default_rules,
)

DOCTYPES = [
	"design_verification_logo_phrase",
	"design_verification_gov_text",
	"design_verification_checklist",
	"design_verification_check_rule",
	"design_verification_settings",
]


def _import_doctype(folder: str):
	dt = _doctype_name(folder)
	app_path = frappe.get_app_path("production_entry")
	json_path = os.path.join(app_path, "production_planning", "doctype", folder, f"{folder}.json")
	if not os.path.isfile(json_path):
		return
	if not frappe.db.exists("DocType", dt):
		import_file_by_path(json_path, force=True, ignore_version=True)
	frappe.clear_cache(doctype=dt)


def _doctype_name(folder: str) -> str:
	return " ".join(w.capitalize() for w in folder.split("_"))


def execute():
	for folder in DOCTYPES:
		_import_doctype(folder)

	_seed_settings()
	frappe.db.commit()


def _seed_settings():
	if not frappe.db.exists("DocType", "Design Verification Settings"):
		return

	settings = frappe.get_single("Design Verification Settings")
	if settings.check_rules:
		# already seeded
		if not settings.logo_phrases:
			_seed_phrases(settings)
		return

	settings.enabled = 1
	settings.customer_field_source = settings.customer_field_source or "Design Name"
	settings.approved_threshold = settings.approved_threshold or 90
	settings.review_threshold = settings.review_threshold or 70
	settings.mm_tolerance = settings.mm_tolerance or 2.0

	for rule in get_all_default_rules():
		settings.append(
			"check_rules",
			{
				"bag_type": rule["bag_type"],
				"sno": rule["sno"],
				"particulars": rule["particulars"],
				"sub_item": rule["sub_item"],
				"sub_particular": rule["sub_particular"],
				"check_item": rule["check_item"],
				"expected_measurement": rule["expected_measurement"],
				"check_method": rule["check_method"],
				"rule_config": json.dumps(rule["rule_config"]) if rule["rule_config"] else "{}",
				"required_for_score": rule["required_for_score"],
				"sort_order": rule["sort_order"],
			},
		)

	_seed_phrases(settings)
	settings.save(ignore_permissions=True)


def _seed_phrases(settings):
	if not settings.logo_phrases:
		for phrase in DEFAULT_LOGO_PHRASES:
			settings.append("logo_phrases", {"phrase": phrase})
	if not settings.mandatory_government_text:
		for row in DEFAULT_GOV_PHRASES:
			settings.append(
				"mandatory_government_text",
				{"phrase": row["phrase"], "required": row["required"]},
			)
