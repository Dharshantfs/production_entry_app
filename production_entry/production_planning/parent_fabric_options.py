# -*- coding: utf-8 -*-
"""Allowed values for Planning sheet custom_parent_fabric (Select field)."""

import re

_STANDALONE_CHAIN_PB_RE = re.compile(r"^\d{3} PB$")

PARENT_FABRIC_OPTIONS = (
	"\nBag FG"
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


def sync_parent_fabric_field_options_to_db():
	"""Push PARENT_FABRIC_OPTIONS to Custom Field metadata (required before save validation)."""
	try:
		import frappe

		for dt in ("Planning Table", "Planning sheet Item"):
			cf_name = frappe.db.get_value(
				"Custom Field",
				{"dt": dt, "fieldname": "custom_parent_fabric"},
				"name",
			)
			if cf_name:
				frappe.db.set_value(
					"Custom Field",
					cf_name,
					"options",
					PARENT_FABRIC_OPTIONS,
					update_modified=False,
				)
		frappe.db.commit()
	except Exception:
		pass
