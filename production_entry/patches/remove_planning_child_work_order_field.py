# -*- coding: utf-8 -*-
"""Remove work_order field from Planning sheet Item and Planning Table (UI + metadata)."""
import frappe

from production_entry.production_planning.parent_fabric_options import (
	_clear_field_property_setters,
	_dedupe_docfield_rows,
	_delete_custom_fields,
)


def _remove_work_order_field(doctype_name):
	if not frappe.db.exists("DocType", doctype_name):
		return
	_delete_custom_fields(doctype_name, "work_order")
	_dedupe_docfield_rows(doctype_name, "work_order")
	for row in frappe.get_all(
		"DocField",
		filters={"parent": doctype_name, "fieldname": "work_order"},
		pluck="name",
	):
		try:
			frappe.delete_doc("DocField", row.name, force=1)
		except Exception:
			try:
				frappe.db.delete("DocField", {"name": row.name})
			except Exception:
				pass
	_clear_field_property_setters(doctype_name, "work_order")
	doc = frappe.get_doc("DocType", doctype_name)
	unique = []
	seen = set()
	for row in doc.fields:
		if not row.fieldname or row.fieldname in seen:
			continue
		if row.fieldname == "work_order":
			continue
		seen.add(row.fieldname)
		unique.append(row)
	if len(unique) != len(doc.fields):
		doc.fields = []
		for idx, row in enumerate(unique, start=1):
			row.idx = idx
			doc.fields.append(row)
		doc.flags.ignore_validate = True
		doc.save(ignore_permissions=True)
	frappe.clear_cache(doctype=doctype_name)


def execute():
	for dt in ("Planning Table", "Planning sheet Item"):
		_remove_work_order_field(dt)
	try:
		frappe.reload_doc("production_planning", "doctype", "planning_table")
		frappe.reload_doc("production_planning", "doctype", "planning_sheet_item")
	except Exception:
		pass
	frappe.db.commit()
