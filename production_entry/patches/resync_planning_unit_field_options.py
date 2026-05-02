# -*- coding: utf-8 -*-
"""Force Planning Table / Planning sheet Item `unit` Select options in DB (VR + Slitting + base list).

Clears Property Setter overrides on `unit` options so Desk reads the canonical list including
VR - 1200MM BOPP PRINTING MACHINE. Safe to re-run.
"""

import frappe

CANONICAL_UNIT_OPTIONS = (
	"UNASSIGNED\nUnit 1\nUnit 2\nUnit 3\nUnit 4\n"
	"Lamination Unit\nSlitting Unit\nVR - 1200MM BOPP PRINTING MACHINE"
)


def execute():
	for dt in ("Planning Table", "Planning sheet Item"):
		frappe.db.sql(
			"""
			UPDATE `tabDocField`
			SET `options`=%s
			WHERE `parent`=%s AND `fieldname`=%s AND `fieldtype`='Select'
			""",
			(CANONICAL_UNIT_OPTIONS, dt, "unit"),
		)
		for ps in frappe.get_all(
			"Property Setter",
			filters={"doc_type": dt, "field_name": "unit", "property": "options"},
			pluck="name",
		) or []:
			try:
				frappe.delete_doc("Property Setter", ps, force=True, ignore_missing=True)
			except Exception:
				pass
	frappe.clear_cache(doctype="Planning Table")
	frappe.clear_cache(doctype="Planning sheet Item")
	frappe.db.commit()
