# -*- coding: utf-8 -*-
"""Merge :mod:`scheduler_api` document hooks with core Planning sheet handlers."""

import frappe
from frappe.utils import cint

from production_entry.production_planning.doctype.planning_sheet.planning_sheet import (
	allocate_unit,
	update_queue,
)
from production_entry.production_planning.scheduler_api import (
	ensure_child_table_schema_for_planning_cancel,
	normalize_planning_sheet_customer_link,
	validate_planning_sheet_duplicates,
)


def planning_sheet_before_validate(doc, method=None):
	normalize_planning_sheet_customer_link(doc, method)


def planning_sheet_validate_combined(doc, method=None):
	validate_planning_sheet_duplicates(doc, method)


def planning_sheet_before_cancel(doc, method=None):
	ensure_child_table_schema_for_planning_cancel(doc, method)


def planning_sheet_allocate_unit(doc, method=None):
	allocate_unit(doc, method)


def planning_sheet_update_queue(doc, method=None):
	update_queue(doc, method)


def planning_sheet_on_update(doc, method=None):
	"""Stamp Parent Child Trace ID on every save (DB write; survives desk read_only fields)."""
	if not doc or not doc.name or cint(getattr(doc, "docstatus", 0)) != 0:
		return
	try:
		from production_entry.production_planning.scheduler_api import (
			ensure_all_planning_sheet_trace_ids,
		)

		result = ensure_all_planning_sheet_trace_ids(doc.name) or {}
		if cint(result.get("updated") or 0) > 0:
			frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "planning_sheet_on_update:ensure_all_planning_sheet_trace_ids")
