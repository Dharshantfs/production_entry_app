# -*- coding: utf-8 -*-
"""Remove duplicate Roll Waste Row custom fields and backfill roll_number from batch_no."""

import frappe
from frappe.utils import cint


def _roll_number_from_batch(batch_no: str) -> int:
	bn = (batch_no or "").strip()
	if not bn or "/" not in bn:
		return 0
	try:
		return int(bn.rsplit("/", 1)[-1].strip())
	except (TypeError, ValueError):
		return 0


def execute():
	# item_code / item_name are standard DocType fields; drop stray Custom Fields.
	for fieldname in ("item_code", "item_name"):
		for name in frappe.get_all(
			"Custom Field",
			filters={"dt": "Roll Waste Row", "fieldname": fieldname},
			pluck="name",
		):
			frappe.delete_doc("Custom Field", name, force=1, ignore_permissions=True)

	meta = frappe.get_meta("Roll Waste Row", cached=False)
	if not meta.has_field("roll_number"):
		return

	for row in frappe.get_all(
		"Roll Waste Row",
		fields=["name", "batch_no", "source_roll", "roll_number"],
		limit_page_length=0,
	):
		if cint(row.roll_number) > 0:
			continue
		batch_no = (row.batch_no or row.source_roll or "").strip()
		rn = _roll_number_from_batch(batch_no)
		if rn > 0:
			frappe.db.set_value("Roll Waste Row", row.name, "roll_number", rn, update_modified=False)

	frappe.clear_cache(doctype="Roll Waste Row")
	frappe.db.commit()
