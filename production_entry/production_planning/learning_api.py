# -*- coding: utf-8 -*-
"""Whitelisted API for Production Learning desk page."""

from __future__ import annotations

import frappe

from production_entry.production_planning.learning_catalog import (
	get_catalog_entries,
	get_lesson,
	get_recommended_path,
)


@frappe.whitelist()
def get_learning_catalog(phase: str = "fabric"):
	"""List fabric (or future bag) processes for the learning home grid."""
	return {
		"phase": phase or "fabric",
		"recommended_path": get_recommended_path(),
		"items": get_catalog_entries(phase=phase or "fabric"),
	}


@frappe.whitelist()
def get_learning_lesson(process_code: str):
	"""Full slideshow + walkthrough steps for one process."""
	lesson = get_lesson(process_code)
	if not lesson:
		frappe.throw(
			frappe._("No learning lesson found for process {0}.").format(process_code),
			frappe.DoesNotExistError,
		)
	return lesson
