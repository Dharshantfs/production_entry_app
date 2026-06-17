# -*- coding: utf-8 -*-
"""Show W/D Cut company field only on w-cut-d-cut-board access rows."""
from __future__ import annotations

import frappe


def execute():
	if not frappe.db.exists("DocType", "Production Board Access Board"):
		return
	frappe.reload_doc("production_planning", "doctype", "production_board_access_board")
	frappe.clear_cache(doctype="Production Board Access Board")
	frappe.db.commit()
