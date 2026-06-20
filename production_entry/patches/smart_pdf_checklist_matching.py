# -*- coding: utf-8 -*-
"""Smart PDF checklist matching: show editable checklist, bag_size_inches, unhide grid."""

import json

import frappe

from production_entry.production_planning.design_verification.constants import get_all_default_rules


def _add_field(docdict):
	key = f"{docdict['dt']}-{docdict['fieldname']}"
	try:
		if frappe.db.exists("Custom Field", key):
			return
		frappe.get_doc({"doctype": "Custom Field", **docdict}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"smart_pdf_field_{docdict.get('fieldname')}")


def _update_field(dt, fieldname, updates):
	key = f"{dt}-{fieldname}"
	if not frappe.db.exists("Custom Field", key):
		return
	try:
		doc = frappe.get_doc("Custom Field", key)
		for k, v in updates.items():
			setattr(doc, k, v)
		doc.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"smart_pdf_update_{fieldname}")


def _refresh_check_rules():
	if not frappe.db.exists("DocType", "Design Verification Settings"):
		return
	settings = frappe.get_single("Design Verification Settings")
	settings.set("check_rules", [])
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
	if not getattr(settings, "color_detection_mode", None):
		settings.color_detection_mode = "Hybrid"
	settings.save(ignore_permissions=True)


def execute():
	dt = None
	for candidate in ("DESIGN MASTER", "Design Master", "Design master"):
		if frappe.db.exists("DocType", candidate):
			dt = candidate
			break
	if not dt:
		return

	meta = frappe.get_meta(dt)
	if not meta.has_field("bag_size_inches"):
		anchor = "top_folding" if meta.has_field("top_folding") else "gusset"
		_add_field({
			"dt": dt,
			"label": "Bag Size (inches)",
			"fieldname": "bag_size_inches",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": anchor,
		})

	if meta.has_field("design_verification_checklist"):
		_update_field(dt, "design_verification_checklist", {"hidden": 0})

	frappe.clear_cache(doctype=dt)

	if frappe.db.exists("DocType", "Design Verification Checklist"):
		frappe.reload_doc("Production Planning", "doctype", "design_verification_checklist")

	if frappe.db.exists("DocType", "Design Verification Check Rule"):
		frappe.reload_doc("Production Planning", "doctype", "design_verification_check_rule")

	if frappe.db.exists("DocType", "Design Verification Settings"):
		frappe.reload_doc("Production Planning", "doctype", "design_verification_settings")
		_refresh_check_rules()
