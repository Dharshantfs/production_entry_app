# -*- coding: utf-8 -*-
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

PARENT_FABRIC_OPTIONS = (
	"\nBag FG"
	"\nMain Fabric"
	"\nLoop Fabric"
	"\n102 Base Fabric"
	"\n103 Base Fabric"
	"\n104 Base Fabric"
	"\n105 Base Fabric"
	"\n106 Base Fabric"
	"\n107 Base Fabric"
	"\nPB"
)


def execute():
	create_custom_fields(
		{
			"Planning Table": [
				{
					"fieldname": "custom_parent_fabric",
					"label": "Parent Fabric",
					"fieldtype": "Select",
					"options": PARENT_FABRIC_OPTIONS,
					"read_only": 1,
					"insert_after": "custom_parent_child_trace_id",
					"in_list_view": 1,
				}
			],
			"Planning sheet Item": [
				{
					"fieldname": "custom_parent_fabric",
					"label": "Parent Fabric",
					"fieldtype": "Select",
					"options": PARENT_FABRIC_OPTIONS,
					"read_only": 1,
					"insert_after": "custom_parent_child_trace_id",
					"in_list_view": 1,
				}
			],
		},
		ignore_validate=True,
		update=True,
	)
	frappe.db.commit()
