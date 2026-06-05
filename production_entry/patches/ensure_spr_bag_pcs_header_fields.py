# -*- coding: utf-8 -*-
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Shaft Production Run": [
				{
					"fieldname": "custom_total_planned_pcs",
					"label": "Total Planned Qty (PCS)",
					"fieldtype": "Float",
					"precision": 0,
					"read_only": 1,
					"depends_on": "eval:doc.custom_is_box_bag",
					"insert_after": "custom_total_planned_qty",
				},
				{
					"fieldname": "custom_total_achieved_pcs",
					"label": "Total Achieved PCS",
					"fieldtype": "Float",
					"precision": 0,
					"read_only": 1,
					"depends_on": "eval:doc.custom_is_box_bag",
					"insert_after": "custom_total_planned_pcs",
				},
			],
		},
		ignore_validate=True,
		update=True,
	)
	frappe.db.commit()
