# -*- coding: utf-8 -*-
"""Add Slitting Order Table and Production Learning to Production Board Access picker."""
from __future__ import annotations

import frappe

from production_entry.production_planning.board_access import sync_board_access_board_field_options


def execute():
	if not frappe.db.exists("DocType", "Production Board Access Board"):
		return
	sync_board_access_board_field_options()
	frappe.clear_cache(doctype="Production Board Access Board")
	frappe.clear_cache(doctype="Production Board Access")
	frappe.db.commit()
