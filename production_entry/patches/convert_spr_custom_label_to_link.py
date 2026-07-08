# -*- coding: utf-8 -*-
"""Convert SPR custom_label from Select to Link → Label Template (field type only).

Does not create or modify the Label Template DocType — that lives on the site already.
"""

import frappe

LABEL_FIELD_DOCTYPES = (
	"Shaft Production Run",
	"Production Plan",
	"Roll Production Entry",
	"Planning sheet",
)


def execute():
	_convert_custom_label_fields()
	frappe.clear_cache()
	frappe.db.commit()


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
