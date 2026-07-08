# -*- coding: utf-8 -*-
"""Convert SPR custom_label from Select to Link → Label Template; seed legacy options."""

import os

import frappe
from frappe.modules.import_file import import_file_by_path

LEGACY_LABEL_OPTIONS = (
	"Default",
	"Reliance",
	"Perfect",
	"Plain CC",
	"Plain",
	"Customized",
)

LABEL_FIELD_DOCTYPES = (
	"Shaft Production Run",
	"Production Plan",
	"Roll Production Entry",
	"Planning sheet",
)


def execute():
	_ensure_label_template_doctype()
	_seed_legacy_label_templates()
	_convert_custom_label_fields()
	_migrate_custom_label_values()
	frappe.clear_cache()
	frappe.db.commit()


def _ensure_label_template_doctype():
	if frappe.db.exists("DocType", "Label Template"):
		return
	app_path = frappe.get_app_path("production_entry")
	json_path = os.path.join(
		app_path,
		"production_planning",
		"doctype",
		"label_template",
		"label_template.json",
	)
	if os.path.isfile(json_path):
		import_file_by_path(json_path, force=True, ignore_version=True)
		frappe.clear_cache(doctype="Label Template")


def _seed_legacy_label_templates():
	for name in LEGACY_LABEL_OPTIONS:
		if frappe.db.exists("Label Template", name):
			continue
		doc = frappe.new_doc("Label Template")
		doc.template_name = name
		doc.is_active = 1
		doc.insert(ignore_permissions=True)


def _convert_custom_label_fields():
	for dt in LABEL_FIELD_DOCTYPES:
		frappe.db.sql(
			"""
			UPDATE `tabDocField`
			SET fieldtype = 'Link', options = 'Label Template'
			WHERE parent = %s AND fieldname = 'custom_label'
			""",
			dt,
		)
		frappe.db.sql(
			"""
			UPDATE `tabCustom Field`
			SET fieldtype = 'Link', options = 'Label Template'
			WHERE dt = %s AND fieldname = 'custom_label'
			""",
			dt,
		)
		frappe.db.sql(
			"""
			DELETE FROM `tabProperty Setter`
			WHERE doc_type = %s
			AND field_name = 'custom_label'
			AND property IN ('fieldtype', 'options')
			""",
			dt,
		)
		frappe.clear_cache(doctype=dt)

	frappe.reload_doc("production_planning", "doctype", "shaft_production_run", force=True)


def _migrate_custom_label_values():
	existing = {n.lower(): n for n in frappe.get_all("Label Template", pluck="name")}

	def _resolve(value: str) -> str:
		v = (value or "").strip()
		if not v:
			return ""
		if frappe.db.exists("Label Template", v):
			return v
		mapped = existing.get(v.lower())
		return mapped or v

	for dt in ("Shaft Production Run", "Production Plan", "Roll Production Entry"):
		if not frappe.get_meta(dt, cached=False).has_field("custom_label"):
			continue
		for row in frappe.get_all(dt, filters={"custom_label": ["!=", ""]}, fields=["name", "custom_label"]):
			new_val = _resolve(row.custom_label)
			if new_val and new_val != row.custom_label:
				frappe.db.set_value(dt, row.name, "custom_label", new_val, update_modified=False)
