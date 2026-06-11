# -*- coding: utf-8 -*-
"""Ensure VTP-L4 SCREEN PRINTING MACHINE Workstation exists (process 232 box bag board)."""

import frappe

from production_entry.production_planning.planning_doctypes import (
	BOX_BAG_UNIT_L4_SCREEN,
	ensure_planning_workstation_record,
)


def execute():
	ensure_planning_workstation_record(BOX_BAG_UNIT_L4_SCREEN)
	frappe.db.commit()
