# -*- coding: utf-8 -*-
"""Stock movement fields for Planning Sheet bag-process stock check."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Planning sheet": [
				{
					"fieldname": "custom_stock_check_mode",
					"label": "Stock Check Mode",
					"fieldtype": "Select",
					"options": "Manual\nAuto",
					"default": "Manual",
					"insert_after": "custom_plan_code",
					"in_list_view": 0,
				}
			],
			"Planning Table": [
				{
					"fieldname": "custom_stock_locked",
					"label": "Stock Locked",
					"fieldtype": "Check",
					"default": "0",
					"insert_after": "custom_movement_type",
					"read_only": 1,
				},
				{
					"fieldname": "custom_stock_batch_no",
					"label": "Stock Batch No",
					"fieldtype": "Link",
					"options": "Batch",
					"insert_after": "custom_stock_locked",
					"read_only": 1,
				},
				{
					"fieldname": "custom_stock_warehouse",
					"label": "Stock Warehouse",
					"fieldtype": "Link",
					"options": "Warehouse",
					"insert_after": "custom_stock_batch_no",
					"read_only": 1,
				},
				{
					"fieldname": "custom_stock_company",
					"label": "Stock Company",
					"fieldtype": "Link",
					"options": "Company",
					"insert_after": "custom_stock_warehouse",
					"read_only": 1,
				},
			],
			"Planning sheet Item": [
				{
					"fieldname": "custom_stock_locked",
					"label": "Stock Locked",
					"fieldtype": "Check",
					"default": "0",
					"insert_after": "custom_movement_type",
					"read_only": 1,
				},
				{
					"fieldname": "custom_stock_batch_no",
					"label": "Stock Batch No",
					"fieldtype": "Link",
					"options": "Batch",
					"insert_after": "custom_stock_locked",
					"read_only": 1,
				},
				{
					"fieldname": "custom_stock_warehouse",
					"label": "Stock Warehouse",
					"fieldtype": "Link",
					"options": "Warehouse",
					"insert_after": "custom_stock_batch_no",
					"read_only": 1,
				},
				{
					"fieldname": "custom_stock_company",
					"label": "Stock Company",
					"fieldtype": "Link",
					"options": "Company",
					"insert_after": "custom_stock_warehouse",
					"read_only": 1,
				},
			],
		},
		ignore_validate=True,
		update=True,
	)
	_update_movement_type_options()
	frappe.clear_cache(doctype="Planning Table")
	frappe.clear_cache(doctype="Planning sheet Item")
	frappe.db.commit()


def _update_movement_type_options():
	opts = "Despatch\nTransfer\nStock"
	for dt in ("Planning Table", "Planning sheet Item"):
		cf = frappe.db.get_value(
			"Custom Field",
			{"dt": dt, "fieldname": "custom_movement_type"},
			"name",
		)
		if cf:
			frappe.db.set_value("Custom Field", cf, "options", opts, update_modified=False)


def _cstr(v):
	return str(v).strip() if v is not None else ""
