"""Ensure Running Patty Wastage Row.recycle_to_next (Check) exists.

If the field is already a Custom Field on the site, leave it. If the DocType
now owns it, drop the duplicate Custom Field so GSM and desk stay in sync.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


FIELDNAME = "recycle_to_next"
DT = "Running Patty Wastage Row"


def execute():
	if not frappe.db.exists("DocType", DT):
		return

	cf_filters = {"dt": DT, "fieldname": FIELDNAME}
	has_docfield = frappe.db.exists("DocField", {"parent": DT, "fieldname": FIELDNAME})
	has_custom = frappe.db.exists("Custom Field", cf_filters)

	if has_docfield and has_custom:
		cf_name = frappe.db.get_value("Custom Field", cf_filters, "name")
		if cf_name:
			frappe.delete_doc("Custom Field", cf_name, force=1, ignore_permissions=True)
		frappe.clear_cache(doctype=DT)
		return

	if has_docfield or has_custom:
		return

	try:
		if frappe.get_meta(DT).has_field(FIELDNAME):
			return
	except Exception:
		pass

	create_custom_fields(
		{
			DT: [
				{
					"fieldname": FIELDNAME,
					"label": "Recycle to Next",
					"fieldtype": "Check",
					"insert_after": "wastage",
					"in_list_view": 1,
					"default": "0",
				}
			]
		},
		update=False,
	)
	frappe.clear_cache(doctype=DT)
