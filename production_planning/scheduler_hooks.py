# -*- coding: utf-8 -*-
"""Merge :mod:`scheduler_api` document hooks with core Planning sheet handlers."""

from production_entry.production_planning.doctype.planning_sheet.planning_sheet import (
	allocate_unit,
	update_queue,
	validate_planning_sheet,
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
	validate_planning_sheet(doc, method)


def planning_sheet_before_cancel(doc, method=None):
	ensure_child_table_schema_for_planning_cancel(doc, method)


def planning_sheet_allocate_unit(doc, method=None):
	allocate_unit(doc, method)


def planning_sheet_update_queue(doc, method=None):
	update_queue(doc, method)
