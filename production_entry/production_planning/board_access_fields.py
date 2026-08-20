# -*- coding: utf-8 -*-
"""Make Production Board Access Unit a Table MultiSelect picker (Frappe v16)."""
from __future__ import annotations

import frappe

from production_entry.production_planning.board_access import CHILD_DOCTYPES, DOCTYPE_ACCESS

_CHILD_TABLE_COLUMNS = {
	"parent": "VARCHAR(140)",
	"parenttype": "VARCHAR(140)",
	"parentfield": "VARCHAR(140)",
	"idx": "INT NOT NULL DEFAULT 0",
}


def ensure_board_access_multiselect_fields():
	"""Convert allowed_units from Table → Table MultiSelect for tag-style Workstation picker."""
	if not frappe.db.exists("DocType", DOCTYPE_ACCESS):
		return

	repair_board_access_child_table_columns()

	meta = frappe.get_meta(DOCTYPE_ACCESS)
	if not meta.has_field("allowed_units"):
		return

	_set_property("allowed_units", "fieldtype", "Table MultiSelect", "Select")
	_cleanup_failed_custom_fields()
	frappe.clear_cache(doctype=DOCTYPE_ACCESS)


def repair_board_access_child_table_columns():
	"""Child tables created manually may lack parent/idx columns required by Frappe."""
	for dt_name in CHILD_DOCTYPES:
		if not frappe.db.exists("DocType", dt_name):
			continue
		if not frappe.db.table_exists(f"tab{dt_name}"):
			continue
		try:
			existing = set(frappe.db.get_table_columns(dt_name) or [])
		except Exception:
			continue
		for col, ddl in _CHILD_TABLE_COLUMNS.items():
			if col not in existing:
				frappe.db.sql(f"ALTER TABLE `tab{dt_name}` ADD COLUMN `{col}` {ddl}")
	frappe.db.commit()


def _set_property(fieldname: str, prop: str, value: str, property_type: str = "Data"):
	existing = frappe.db.get_value(
		"Property Setter",
		{
			"doc_type": DOCTYPE_ACCESS,
			"field_name": fieldname,
			"property": prop,
		},
		"name",
	)
	if existing:
		frappe.db.set_value("Property Setter", existing, "value", value, update_modified=False)
		return

	try:
		frappe.make_property_setter(
			{
				"doctype": DOCTYPE_ACCESS,
				"fieldname": fieldname,
				"property": prop,
				"value": value,
				"property_type": property_type,
			},
			ignore_validate=True,
			is_system_generated=True,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"board_access_fields: set {fieldname}.{prop}")


def _cleanup_failed_custom_fields():
	"""Remove broken custom fields from earlier failed patch attempts."""
	for fieldname in ("allowed_board_slugs", "allowed_workstations"):
		cf = frappe.db.get_value(
			"Custom Field",
			{"dt": DOCTYPE_ACCESS, "fieldname": fieldname},
			"name",
		)
		if cf:
			try:
				frappe.delete_doc("Custom Field", cf, force=True)
			except Exception:
				pass

	for fieldname in ("allowed_units", "allowed_boards", "allowed_color_chart", "allowed_gsm"):
		ps = frappe.db.get_value(
			"Property Setter",
			{
				"doc_type": DOCTYPE_ACCESS,
				"field_name": fieldname,
				"property": "hidden",
			},
			"name",
		)
		if ps:
			try:
				frappe.delete_doc("Property Setter", ps, force=True)
			except Exception:
				pass


def sync_board_access_workstation_multiselect_options():
	"""No-op — Table MultiSelect reads from Workstation DocType directly."""
	return


def migrate_child_table_rows_to_multiselect():
	"""Safe no-op — child table rows work as-is with Table MultiSelect."""
	ensure_board_access_multiselect_fields()
