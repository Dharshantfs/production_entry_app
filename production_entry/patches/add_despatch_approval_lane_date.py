# -*- coding: utf-8 -*-
"""Logistics lane date on Despatch Approval — stable across DN link/delete."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import getdate


def execute():
	create_custom_fields(
		{
			"Despatch Approval": [
				{
					"fieldname": "custom_despatch_lane_date",
					"label": "Despatch Lane Date",
					"fieldtype": "Date",
					"insert_after": "from_company",
					"in_list_view": 1,
				}
			]
		},
		ignore_validate=True,
		update=True,
	)
	if frappe.db.has_column("Despatch Approval", "custom_despatch_lane_date"):
		frappe.db.sql(
			"""
			update `tabDespatch Approval`
			set custom_despatch_lane_date = date(creation)
			where custom_despatch_lane_date is null
			"""
		)
	frappe.db.commit()
