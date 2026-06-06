"""Backfill width_inch on Planning Table 103 rows linked to bag FG sheets."""

import frappe
from frappe.utils import flt

from production_entry.production_planning.scheduler_api import (
	_bom_item_process_code,
	_resolve_planning_row_width_inch,
)


def execute():
	if not frappe.db.table_exists("Planning Table") or not frappe.db.has_column("Planning Table", "width_inch"):
		return
	rows = frappe.db.sql(
		"""
		SELECT pt.name, pt.item_code, pt.parent
		FROM `tabPlanning Table` pt
		INNER JOIN `tabPlanning sheet` ps ON ps.name = pt.parent
		WHERE IFNULL(pt.item_code, '') != ''
		""",
		as_dict=True,
	) or []
	updated = 0
	for r in rows:
		ic = (r.get("item_code") or "").strip()
		if _bom_item_process_code(ic) != "103":
			continue
		cur = flt(frappe.db.get_value("Planning Table", r.get("name"), "width_inch") or 0)
		if cur > 0:
			continue
		w = flt(_resolve_planning_row_width_inch(ic))
		if w <= 0:
			continue
		frappe.db.set_value("Planning Table", r.get("name"), "width_inch", w, update_modified=False)
		updated += 1
	if updated:
		frappe.db.commit()
