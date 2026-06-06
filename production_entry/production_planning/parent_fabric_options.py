# -*- coding: utf-8 -*-
"""Allowed values for Planning sheet custom_parent_fabric (Select field)."""

PARENT_FABRIC_OPTIONS = (
	"\nBag FG"
	"\nMain Fabric"
	"\nLoop Fabric"
	"\n102 Base Fabric"
	"\n103 Base Fabric"
	"\n104 Base Fabric"
	"\n105 Base Fabric"
	"\n106 Base Fabric"
	"\n107 Base Fabric"
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
	"108 Base Fabric": "Loop 108 Base Fabric",
	"110 Base Fabric": "Loop 110 Base Fabric",
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
	return ""
