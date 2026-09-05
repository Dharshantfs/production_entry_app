# -*- coding: utf-8 -*-
"""Show Order Code (party_code) and Customer on the Planning sheet list filter bar."""
import frappe

from production_entry.production_planning.planning_doctypes import (
	LEGACY_PLANNING_SHEET,
	PLANNING_SHEET,
)

FILTER_FIELDS = ("party_code", "customer")


def execute():
	for doctype_name in (PLANNING_SHEET, LEGACY_PLANNING_SHEET):
		if not frappe.db.exists("DocType", doctype_name):
			continue
		for fieldname in FILTER_FIELDS:
			_set_docfield_standard_filter(doctype_name, fieldname)
			_ensure_property_setter(doctype_name, fieldname)
		frappe.clear_cache(doctype=doctype_name)
	frappe.clear_cache()


def _set_docfield_standard_filter(doctype_name, fieldname):
	name = frappe.db.get_value(
		"DocField",
		{"parent": doctype_name, "fieldname": fieldname},
		"name",
	)
	if name:
		frappe.db.set_value("DocField", name, "in_standard_filter", 1, update_modified=False)
		return
	custom = frappe.db.get_value(
		"Custom Field",
		{"dt": doctype_name, "fieldname": fieldname},
		"name",
	)
	if custom:
		frappe.db.set_value("Custom Field", custom, "in_standard_filter", 1, update_modified=False)


def _ensure_property_setter(doctype_name, fieldname):
	if not frappe.db.table_exists("Property Setter"):
		return
	filters = {
		"doc_type": doctype_name,
		"field_name": fieldname,
		"property": "in_standard_filter",
		"doctype_or_field": "DocField",
	}
	existing = frappe.db.get_value("Property Setter", filters, "name")
	if existing:
		if str(frappe.db.get_value("Property Setter", existing, "value") or "") != "1":
			frappe.db.set_value("Property Setter", existing, "value", "1", update_modified=False)
		return
	try:
		ps = frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doctype_or_field": "DocField",
				"doc_type": doctype_name,
				"field_name": fieldname,
				"property": "in_standard_filter",
				"property_type": "Check",
				"value": "1",
			}
		)
		ps.flags.ignore_permissions = True
		ps.insert()
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"in_standard_filter Property Setter for {doctype_name}.{fieldname}",
		)
