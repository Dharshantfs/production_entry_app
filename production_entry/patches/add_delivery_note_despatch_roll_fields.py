# -*- coding: utf-8 -*-
"""Despatch Approval link + per-item roll JSON on Delivery Note."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Delivery Note": [
				{
					"fieldname": "custom_despatch_approval",
					"label": "Despatch Approval",
					"fieldtype": "Link",
					"options": "Despatch Approval",
					"insert_after": "customer",
					"read_only": 1,
				}
			],
			"Delivery Note Item": [
				{
					"fieldname": "custom_despatch_rolls_json",
					"label": "Despatch Rolls (JSON)",
					"fieldtype": "Small Text",
					"insert_after": "item_code",
					"read_only": 1,
					"hidden": 1,
				}
			],
		},
		ignore_validate=True,
		update=True,
	)
	frappe.db.commit()
