"""GSM Production Entry — additive APIs only. Does not modify Production Table or create_item_spr."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from production_entry.production_planning.doctype.shaft_production_run.shaft_production_run import (
	_cstr,
)


@frappe.whitelist()
def preview_spr_batch_numbers_for_entry(
	unit,
	run_date,
	shift,
	count=1,
	client_max_roll=None,
	client_series_prefix=None,
	existing_batches=None,
):
	"""Read-only batch/roll preview for GSM Production Entry (no SPR document required)."""
	count = cint(count)
	if count < 1:
		return []
	unit = _cstr(unit).strip()
	shift = _cstr(shift).strip()
	if not unit or not run_date or not shift:
		frappe.throw(_("Set Run Date, Unit, and Shift to preview batch numbers."))

	doc = frappe.new_doc("Shaft Production Run")
	doc.run_date = run_date
	doc.custom_unit = unit
	doc.shift = shift

	existing = []
	if existing_batches:
		if isinstance(existing_batches, str):
			try:
				existing = json.loads(existing_batches) or []
			except Exception:
				existing = [x.strip() for x in existing_batches.split(",") if x.strip()]
		elif isinstance(existing_batches, (list, tuple)):
			existing = list(existing_batches)

	for bn in existing:
		bn = _cstr(bn).strip()
		if bn:
			row = doc.append("items", {})
			row.batch_no = bn

	rd = getdate(run_date)
	comp_id, unit_num = doc._batch_prefix_parts()
	root_5 = f"{comp_id}-{unit_num}{rd.month:02d}{rd.year % 100:02d}"
	csp = _cstr(client_series_prefix).strip()
	if csp and csp.startswith(root_5):
		series_prefix = csp
	else:
		series_prefix = doc._resolve_series_prefix(root_5)

	next_roll = doc._next_roll_starting(series_prefix)
	try:
		if client_max_roll is not None and cint(client_max_roll) >= 0:
			next_roll = max(int(next_roll), cint(client_max_roll) + 1)
	except Exception:
		pass

	used_batches = set(existing)
	out = []
	for _i in range(count):
		while f"{series_prefix}/{next_roll}" in used_batches:
			next_roll += 1
		bn = f"{series_prefix}/{next_roll}"
		used_batches.add(bn)
		out.append({"batch_no": bn, "roll_no": next_roll, "series_prefix": series_prefix})
		next_roll += 1
	return out
