# -*- coding: utf-8 -*-
"""Backfill Shaft Production Run list-view Color / Quality / GSM summaries."""
import frappe

from production_entry.production_planning.doctype.shaft_production_run.shaft_production_run import (
	compute_spr_attribute_summaries,
)


def execute():
	doctype = "Shaft Production Run"
	if not frappe.db.has_column(doctype, "custom_color_summary"):
		return

	for fieldname in ("custom_quality_summary", "custom_gsm_summary", "custom_color_summary"):
		frappe.db.set_value(
			"DocField",
			{"parent": doctype, "fieldname": fieldname},
			"in_list_view",
			1,
			update_modified=False,
		)

	for name in frappe.get_all(doctype, pluck="name"):
		doc = frappe.get_doc(doctype, name)
		frappe.db.set_value(
			doctype,
			name,
			compute_spr_attribute_summaries(doc),
			update_modified=False,
		)

	frappe.clear_cache(doctype=doctype)
	frappe.db.commit()
