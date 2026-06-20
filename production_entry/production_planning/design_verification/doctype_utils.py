# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe

_CACHED_DOCTYPE: str | None = None

# Known DocType names across sites (Frappe Cloud custom DocTypes vary in casing).
_CANDIDATE_NAMES = (
	"DESIGN MASTER",
	"Design Master",
	"Design master",
	"design master",
)


def get_design_master_doctype() -> str | None:
	"""Return the installed Design Master DocType name exactly as in the DB."""
	global _CACHED_DOCTYPE
	if _CACHED_DOCTYPE:
		return _CACHED_DOCTYPE

	for name in _CANDIDATE_NAMES:
		if frappe.db.exists("DocType", name):
			_CACHED_DOCTYPE = name
			return name

	try:
		candidates = frappe.get_all(
			"DocType",
			filters={"name": ["like", "%Design%Master%"]},
			pluck="name",
			limit=5,
		)
		for name in candidates:
			if frappe.db.table_exists(name):
				_CACHED_DOCTYPE = name
				return name
	except Exception:
		pass

	return None


def is_design_master_doc(doc) -> bool:
	dt = get_design_master_doctype()
	return bool(dt and getattr(doc, "doctype", None) == dt)


def clear_design_master_doctype_cache():
	global _CACHED_DOCTYPE
	_CACHED_DOCTYPE = None
