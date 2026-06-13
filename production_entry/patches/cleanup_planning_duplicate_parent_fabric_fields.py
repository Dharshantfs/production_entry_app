# -*- coding: utf-8 -*-
"""Remove duplicate Parent Fabric Custom Fields on planning child tables."""
from production_entry.production_planning.parent_fabric_options import repair_planning_child_table_metadata


def execute():
	repair_planning_child_table_metadata()
