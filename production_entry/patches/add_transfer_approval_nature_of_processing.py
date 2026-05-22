# -*- coding: utf-8 -*-
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Transfer Approval": [
				{
					"fieldname": "nature_of_processing",
					"label": "Nature of Processing",
					"fieldtype": "Data",
					"insert_after": "to_destination_label",
					"in_list_view": 1,
					"reqd": 0,
				}
			]
		},
		ignore_validate=True,
		update=True,
	)
	frappe.db.commit()
