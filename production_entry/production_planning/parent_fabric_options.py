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
	# Hard delete any rows left (corrupt / partial deletes).
	try:
		frappe.db.delete("Custom Field", {"dt": dt, "fieldname": fieldname})
	except Exception:
		pass


def _dedupe_docfield_rows(dt, fieldname):
	"""Keep a single DocField row per fieldname (legacy migrate/import duplicates)."""
	import frappe

	names = frappe.get_all(
		"DocField",
		filters={"parent": dt, "fieldname": fieldname},
		pluck="name",
		order_by="idx asc, creation asc",
	)
	for name in names[1:]:
		try:
			frappe.delete_doc("DocField", name, force=1)
		except Exception:
			try:
				frappe.db.delete("DocField", {"name": name})
			except Exception:
				pass


def _dedupe_doctype_fields_and_field_order(doctype_name):
	"""Reload DocType child rows + field_order so each fieldname appears once."""
	import json

	import frappe

	_delete_custom_fields(doctype_name, "custom_parent_fabric")
	_dedupe_docfield_rows(doctype_name, "custom_parent_fabric")

	doc = frappe.get_doc("DocType", doctype_name)
	seen = set()
	unique = []
	for row in doc.fields:
		fn = row.fieldname
		if not fn or fn in seen:
			continue
		seen.add(fn)
		unique.append(row)

	if len(unique) != len(doc.fields):
		doc.fields = []
		for idx, row in enumerate(unique, start=1):
			row.idx = idx
			doc.fields.append(row)

	# field_order is not on DocType in older Frappe — dedupe DocField rows only.
	dt_meta = frappe.get_meta("DocType")
	if dt_meta.has_field("field_order"):
		field_order = getattr(doc, "field_order", None)
		if isinstance(field_order, str):
			try:
				field_order = json.loads(field_order)
			except Exception:
				field_order = []
		if not field_order:
			field_order = [row.fieldname for row in doc.fields]

		seen_order = set()
		clean_order = []
		for fn in field_order:
			if not fn or fn in seen_order:
				continue
			seen_order.add(fn)
			clean_order.append(fn)
		for row in doc.fields:
			if row.fieldname not in seen_order:
				clean_order.append(row.fieldname)
				seen_order.add(row.fieldname)

		doc.set("field_order", json.dumps(clean_order))

	doc.flags.ignore_validate = True
	doc.save(ignore_permissions=True)


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
	"""One Parent Fabric field per doctype (dedupe Custom Field / DocField duplicates)."""
	import frappe

	options = parent_fabric_select_options_text()
	for dt in ("Planning Table", "Planning sheet Item"):
		if not frappe.db.exists("DocType", dt):
			continue
		try:
			frappe.reload_doc("production_planning", "doctype", dt.replace(" ", "_").lower())
		except Exception:
			pass
		_dedupe_doctype_fields_and_field_order(dt)

		doc = frappe.get_doc("DocType", dt)
		changed = False
		for row in doc.fields:
			if row.fieldname == "custom_parent_fabric":
				row.options = options
				row.read_only = 1
				row.in_list_view = 1
				changed = True
		if changed:
			doc.flags.ignore_validate = True
			doc.save(ignore_permissions=True)

		_clear_field_property_setters(dt, "custom_parent_fabric", ("read_only", "in_list_view", "options"))
		frappe.clear_cache(doctype=dt)

	frappe.db.commit()


def sync_parent_fabric_field_options_to_db():
	"""Push PARENT_FABRIC_OPTIONS to DocField metadata (field is on DocType JSON, not Custom Field)."""
	try:
		repair_planning_child_table_metadata()
	except Exception:
		pass
