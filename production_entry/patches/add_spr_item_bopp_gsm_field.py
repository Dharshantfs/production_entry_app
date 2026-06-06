# -*- coding: utf-8 -*-
"""BOPP GSM on Shaft Production Run Item roll lines."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Shaft Production Run Item": [
				{
					"fieldname": "custom_bopp_gsm",
					"label": "BOPP GSM",
					"fieldtype": "Int",
					"insert_after": "custom_lam_gsm",
					"read_only": 1,
					"in_list_view": 0,
				}
			],
		},
		ignore_validate=True,
		update=True,
	)
	frappe.clear_cache(doctype="Shaft Production Run Item")
	frappe.db.commit()
