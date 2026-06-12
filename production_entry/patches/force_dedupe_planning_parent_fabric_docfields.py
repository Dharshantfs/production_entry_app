# -*- coding: utf-8 -*-
"""Force-remove duplicate custom_parent_fabric DocField/Custom Field rows (Customize Form error)."""
from production_entry.production_planning.parent_fabric_options import repair_planning_child_table_metadata


def execute():
	repair_planning_child_table_metadata()
