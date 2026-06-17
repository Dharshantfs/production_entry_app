# -*- coding: utf-8 -*-
"""Assign Shift / Sync SPR freeze columns + W/D Cut company scope on board access rows."""
from __future__ import annotations

import frappe

from production_entry.production_planning.board_access import sync_board_access_board_field_options


def execute():
	if not frappe.db.exists("DocType", "Production Board Access Board"):
		return
	frappe.reload_doc("production_planning", "doctype", "production_board_access_board")
	if frappe.db.exists("DocType", "Production Board Access"):
		frappe.reload_doc("production_planning", "doctype", "production_board_access")
	sync_board_access_board_field_options()
	frappe.clear_cache(doctype="Production Board Access Board")
	frappe.db.commit()
