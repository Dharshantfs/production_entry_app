# -*- coding: utf-8 -*-
"""Convert SPR custom_label from Select to Link → Label Template; seed legacy options."""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def _cstr(value) -> str:
	return "" if value is None else str(value).strip()

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


def _label_template_name_field() -> str:
	"""Return the site naming/title field on Label Template (template_name vs label_name)."""
	meta = frappe.get_meta("Label Template")
	autoname = _cstr(meta.autoname or "")
	if autoname.startswith("field:"):
		fn = autoname.split(":", 1)[1].strip()
		if fn and meta.has_field(fn):
			return fn
	for fn in ("label_name", "template_name", "label"):
		if meta.has_field(fn):
			return fn
	return "template_name"


def _label_template_exists(name: str) -> bool:
	n = _cstr(name).strip()
	if not n:
		return False
	if frappe.db.exists("Label Template", n):
		return True
	lower = n.lower()
	name_field = _label_template_name_field()
	fields = ["name"]
	if name_field:
		fields.append(name_field)
	for row in frappe.get_all("Label Template", fields=fields):
		if _cstr(row.name).lower() == lower:
			return True
		if name_field and _cstr(row.get(name_field)).lower() == lower:
			return True
	return False


def _ensure_label_template_record(name: str) -> None:
	n = _cstr(name).strip()
	if not n or _label_template_exists(n):
		return
	name_field = _label_template_name_field()
	doc = frappe.new_doc("Label Template")
	doc.set(name_field, n)
	if frappe.get_meta("Label Template").has_field("is_active"):
		doc.is_active = 1
	try:
		doc.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"Label Template seed failed for {n!r} (field={name_field})",
		)


def _seed_legacy_label_templates():
	if not frappe.db.exists("DocType", "Label Template"):
		return
	for name in LEGACY_LABEL_OPTIONS:
		_ensure_label_template_record(name)


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
	name_field = _label_template_name_field() if frappe.db.exists("DocType", "Label Template") else ""
	existing_by_lower: dict[str, str] = {}
	for row in frappe.get_all("Label Template", fields=["name", name_field] if name_field else ["name"]):
		existing_by_lower[_cstr(row.name).lower()] = row.name
		if name_field:
			title = _cstr(row.get(name_field))
			if title:
				existing_by_lower[title.lower()] = row.name

	def _resolve(value: str) -> str:
		v = _cstr(value)
		if not v:
			return ""
		if frappe.db.exists("Label Template", v):
			return v
		return existing_by_lower.get(v.lower(), v)

	for dt in ("Shaft Production Run", "Production Plan", "Roll Production Entry"):
		if not frappe.get_meta(dt, cached=False).has_field("custom_label"):
			continue
		for row in frappe.get_all(dt, filters={"custom_label": ["!=", ""]}, fields=["name", "custom_label"]):
			new_val = _resolve(row.custom_label)
			if new_val and new_val != row.custom_label:
				frappe.db.set_value(dt, row.name, "custom_label", new_val, update_modified=False)
