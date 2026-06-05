# -*- coding: utf-8 -*-
"""Remove Custom Field rows that duplicate fields already on Shaft Production Run DocType JSON."""
import frappe

# Fieldnames shipped in shaft_production_run.json — Custom Field copies render twice on the form.
_SPR_STANDARD_FIELDNAMES = (
	"company",
	"custom_total_planned_pcs",
	"custom_total_achieved_pcs",
)

# Site tables that should only show for non-bag SPR (hide when Is Bag is checked).
_SPR_BAG_HIDDEN_TABLE_FIELDS = (
	"custom_core_details",
	"custom_polybag_details",
	"custom_running_patty_wastage",
)


def execute():
	doctype = "Shaft Production Run"
	meta = frappe.get_meta(doctype, cached=False)

	for fn in _SPR_STANDARD_FIELDNAMES:
		if not meta.has_field(fn):
			continue
		for row in frappe.get_all(
			"Custom Field",
			filters={"dt": doctype, "fieldname": fn},
			fields=["name"],
		):
			try:
				frappe.delete_doc("Custom Field", row.name, force=1)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"cleanup_spr_duplicate: {fn}")

	for fn in _SPR_BAG_HIDDEN_TABLE_FIELDS:
		cf_name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fn})
		if not cf_name:
			continue
		try:
			frappe.db.set_value(
				"Custom Field",
				cf_name,
				"depends_on",
				"eval:!doc.custom_is_box_bag",
				update_modified=False,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"cleanup_spr_bag_hide: {fn}")

	frappe.clear_cache(doctype=doctype)
	frappe.db.commit()
