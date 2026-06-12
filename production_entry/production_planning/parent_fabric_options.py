# -*- coding: utf-8 -*-
"""Allowed values for Planning sheet custom_parent_fabric (Select field)."""

import re

_STANDALONE_CHAIN_PB_RE = re.compile(r"^\d{3} PB$")

PARENT_FABRIC_OPTIONS = (
	"\nBag FG"
	"\n232 RM Bag"
	"\n231 Main Fabric"
	"\n231 Loop Fabric"
	"\nFG Fabric"
	"\nFG Sheet"
	"\nMain Fabric"
	"\nLoop Fabric"
	"\n102 Base Fabric"
	"\n103 Base Fabric"
	"\n104 Base Fabric"
	"\n105 Base Fabric"
	"\n106 Base Fabric"
	"\n107 Base Fabric"
	"\n108 Base Fabric"
	"\n110 Base Fabric"
	"\n251 Base Fabric"
	"\n252 Base Fabric"
	"\n253 Base Fabric"
	"\n254 Base Fabric"
	"\n255 Base Fabric"
	"\nPB"
	"\nMain 102 Base Fabric"
	"\nMain 103 Base Fabric"
	"\nMain 104 Base Fabric"
	"\nMain 105 Base Fabric"
	"\nMain 106 Base Fabric"
	"\nMain 107 Base Fabric"
	"\nMain 107 PB"
	"\nLoop 103 Base Fabric"
	"\nLoop 108 Base Fabric"
	"\nLoop 110 Base Fabric"
	"\nLoop 107 Base Fabric"
	"\nLoop 107 PB"
)

PARENT_FABRIC_OPTION_SET = frozenset(
	opt.strip() for opt in PARENT_FABRIC_OPTIONS.split("\n") if opt.strip()
)

# Legacy / mistaken labels from older stamp logic → current Select options.
_PARENT_FABRIC_ALIASES = {
	"103 Base Fabric": "Loop 103 Base Fabric",
}


def normalize_parent_fabric_label(label):
	"""Return a value allowed by the Parent Fabric Select field."""
	val = str(label or "").strip()
	if not val:
		return ""
	val = _PARENT_FABRIC_ALIASES.get(val, val)
	if val in PARENT_FABRIC_OPTION_SET:
		return val
	# Standalone fabric chains stamp "{parent} PB" (e.g. 107 PB) — map to Select option PB.
	if _STANDALONE_CHAIN_PB_RE.match(val) and "PB" in PARENT_FABRIC_OPTION_SET:
		return "PB"
	return ""


def parent_fabric_select_options_text():
	"""Newline-separated options for Select metadata (no leading blank line)."""
	return "\n".join(opt.strip() for opt in PARENT_FABRIC_OPTIONS.split("\n") if opt.strip())


def _delete_custom_fields(dt, fieldname):
	import frappe

	for cf in frappe.get_all(
		"Custom Field",
		filters={"dt": dt, "fieldname": fieldname},
		pluck="name",
	):
		try:
			frappe.delete_doc("Custom Field", cf, force=1)
		except Exception:
			pass


def _dedupe_docfield_rows(dt, fieldname):
	"""Keep a single DocField row per fieldname (legacy migrate/import duplicates)."""
	import frappe

	rows = frappe.get_all(
		"DocField",
		filters={"parent": dt, "fieldname": fieldname},
		fields=["name", "idx"],
		order_by="idx asc, creation asc",
	)
	for row in rows[1:]:
		try:
			frappe.delete_doc("DocField", row.name, force=1)
		except Exception:
			try:
				frappe.db.delete("DocField", {"name": row.name})
			except Exception:
				pass


def _clear_field_property_setters(dt, fieldname, properties=None):
	import frappe

	properties = properties or ("read_only",)
	for prop in properties:
		for ps_name in frappe.get_all(
			"Property Setter",
			filters={"doc_type": dt, "field_name": fieldname, "property": prop},
			pluck="name",
		):
			try:
				frappe.delete_doc("Property Setter", ps_name, force=1)
			except Exception:
				pass


def repair_planning_child_table_metadata():
	"""One Parent Fabric field per doctype; Work Order editable on Items + board."""
	import frappe

	options = parent_fabric_select_options_text()
	for dt in ("Planning Table", "Planning sheet Item"):
		if not frappe.db.exists("DocType", dt):
			continue
		_delete_custom_fields(dt, "custom_parent_fabric")
		_dedupe_docfield_rows(dt, "custom_parent_fabric")
		pf_filter = {"parent": dt, "fieldname": "custom_parent_fabric"}
		if frappe.db.exists("DocField", pf_filter):
			frappe.db.set_value("DocField", pf_filter, "options", options, update_modified=False)
			frappe.db.set_value("DocField", pf_filter, "read_only", 1, update_modified=False)
			frappe.db.set_value("DocField", pf_filter, "in_list_view", 1, update_modified=False)
		_clear_field_property_setters(dt, "work_order", ("read_only",))
		wo_filter = {"parent": dt, "fieldname": "work_order"}
		if frappe.db.exists("DocField", wo_filter):
			frappe.db.set_value("DocField", wo_filter, "read_only", 0, update_modified=False)
			frappe.db.set_value("DocField", wo_filter, "in_list_view", 1, update_modified=False)
		frappe.clear_cache(doctype=dt)

	try:
		frappe.reload_doc("production_planning", "doctype", "planning_table")
		frappe.reload_doc("production_planning", "doctype", "planning_sheet_item")
	except Exception:
		pass
	frappe.db.commit()


def sync_parent_fabric_field_options_to_db():
	"""Push PARENT_FABRIC_OPTIONS to DocField metadata (field is on DocType JSON, not Custom Field)."""
	try:
		repair_planning_child_table_metadata()
	except Exception:
		pass
