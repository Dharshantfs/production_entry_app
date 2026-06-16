# -*- coding: utf-8 -*-
"""Keep Production Board Access Board Select options in sync with board picker list."""
from __future__ import annotations

import frappe

from production_entry.production_planning.board_access import (
	build_board_picker_select_options,
	sync_board_access_board_field_options,
)


def execute():
	if not frappe.db.exists("DocType", "Production Board Access Board"):
		return
	sync_board_access_board_field_options()
	frappe.clear_cache(doctype="Production Board Access Board")
