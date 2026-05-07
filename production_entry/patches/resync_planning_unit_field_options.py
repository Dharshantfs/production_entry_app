# -*- coding: utf-8 -*-
"""Historical Select-list sync — obsolete now that ``unit`` links to Workstation."""

import frappe


def execute():
	# No-op: kept so the patch id remains valid on sites that already ran it.
	frappe.clear_cache(doctype="Planning Table")
	frappe.clear_cache(doctype="Planning sheet Item")
