# -*- coding: utf-8 -*-
"""Force Planning sheet importable on tabDocType (what Role Permission Manager checks).

Customize Form "Allow Import" only writes a Property Setter. RPM validates
frappe.get_doc("DocType").allow_import from tabDocType, so the checkbox can
look enabled while Delete still fails with:
"Cannot set import as DocType (Planning sheet) is not importable"
"""
import frappe
from frappe.utils import cint

from production_entry.production_planning.planning_doctypes import (
	LEGACY_PLANNING_SHEET,
	PLANNING_SHEET,
)


def execute():
	_enable_planning_sheet_import()


def _enable_planning_sheet_import():
	names = []
	for name in (PLANNING_SHEET, LEGACY_PLANNING_SHEET):
		if frappe.db.exists("DocType", name):
			names.append(name)
	if not names:
		return

	frappe.db.sql(
		"UPDATE `tabDocType` SET allow_import = 1 WHERE name IN ({})".format(
			", ".join(["%s"] * len(names))
		),
		tuple(names),
	)

	for name in names:
		_ensure_allow_import_property_setter(name)
		frappe.clear_cache(doctype=name)

	frappe.clear_cache()


def _ensure_allow_import_property_setter(doctype_name: str):
	"""Keep Customize Form checkbox in sync with the DocType row RPM reads."""
	if not frappe.db.table_exists("Property Setter"):
		return
	existing = frappe.db.get_value(
		"Property Setter",
		{"doc_type": doctype_name, "property": "allow_import", "doctype_or_field": "DocType"},
		"name",
	)
	if existing:
		if str(frappe.db.get_value("Property Setter", existing, "value") or "") != "1":
			frappe.db.set_value("Property Setter", existing, "value", "1", update_modified=False)
		return
	try:
		ps = frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doctype_or_field": "DocType",
				"doc_type": doctype_name,
				"property": "allow_import",
				"property_type": "Check",
				"value": "1",
			}
		)
		ps.flags.ignore_permissions = True
		ps.insert()
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"allow_import Property Setter for {doctype_name}")
