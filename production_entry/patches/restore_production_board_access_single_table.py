# -*- coding: utf-8 -*-
"""Force Production Board Access back to single Allowed Boards table (undo Color Chart/GSM split)."""
from __future__ import annotations

import frappe


CHILD_DOCTYPES = (
	"Production Board Access Color Chart",
	"Production Board Access GSM",
)

FIELDS_TO_REMOVE = (
	"section_break_color_chart",
	"allowed_color_chart",
	"section_break_gsm",
	"allowed_gsm",
)


def execute():
	# Drop split child tables from the parent DocType if they are still on the site.
	if frappe.db.exists("DocType", "Production Board Access"):
		doc = frappe.get_doc("DocType", "Production Board Access")
		changed = False
		keep = []
		for df in doc.fields:
			if df.fieldname in FIELDS_TO_REMOVE:
				changed = True
				continue
			keep.append(df)
		if changed:
			doc.set("fields", keep)
			# Rebuild field_order without removed names
			order = [f.fieldname for f in keep if f.fieldname]
			doc.field_order = order
			doc.flags.ignore_links = True
			doc.flags.ignore_validate = True
			doc.save(ignore_permissions=True)

	# Remove orphan child DocTypes created by the Aug 20 split (safe if unused).
	for name in CHILD_DOCTYPES:
		if not frappe.db.exists("DocType", name):
			continue
		try:
			frappe.delete_doc("DocType", name, force=1, ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"delete_{name}")

	frappe.clear_cache(doctype="Production Board Access")
	frappe.db.commit()
