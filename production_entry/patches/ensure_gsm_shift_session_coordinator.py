# -*- coding: utf-8 -*-
"""Ensure GSM Shift Session.coordinator and Shift Wise Consumable List DocTypes."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	frappe.reload_doc("production_planning", "doctype", "shift_wise_consumable_item")
	frappe.reload_doc("production_planning", "doctype", "shift_wise_consumable_list")
	frappe.reload_doc("production_planning", "doctype", "gsm_shift_session")

	if not frappe.db.exists("DocType", "GSM Shift Session"):
		return
	if frappe.db.has_column("GSM Shift Session", "coordinator"):
		return
	create_custom_fields(
		{
			"GSM Shift Session": [
				{
					"fieldname": "coordinator",
					"label": "Co-ordinator",
					"fieldtype": "Link",
					"options": "Employee",
					"insert_after": "supervisor",
					"ignore_user_permissions": 1,
				}
			]
		},
		update=True,
	)
