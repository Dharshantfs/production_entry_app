# -*- coding: utf-8 -*-
"""Planning sheet ``unit`` must Link to Workstation (not legacy Unit doctype)."""

from production_entry.production_planning.planning_doctypes import (
	ensure_planning_unit_field_links_workstation,
)


def execute():
	ensure_planning_unit_field_links_workstation()
