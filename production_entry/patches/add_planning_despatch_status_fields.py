# -*- coding: utf-8 -*-
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Planning Table": [
				{
					"fieldname": "custom_despatch_status",
					"label": "Despatch Status",
					"fieldtype": "Data",
					"insert_after": "custom_transfer_status",
					"read_only": 1,
				},
				{
					"fieldname": "custom_despatch_approval",
					"label": "Despatch Approval",
					"fieldtype": "Link",
					"options": "Despatch Approval",
					"insert_after": "custom_despatch_status",
					"read_only": 1,
				},
			],
			"Planning sheet Item": [
				{
					"fieldname": "custom_despatch_status",
					"label": "Despatch Status",
					"fieldtype": "Data",
					"insert_after": "custom_transfer_status",
					"read_only": 1,
				},
				{
					"fieldname": "custom_despatch_approval",
					"label": "Despatch Approval",
					"fieldtype": "Link",
					"options": "Despatch Approval",
					"insert_after": "custom_despatch_status",
					"read_only": 1,
				},
			],
		},
		ignore_validate=True,
		update=True,
	)
	frappe.db.commit()
