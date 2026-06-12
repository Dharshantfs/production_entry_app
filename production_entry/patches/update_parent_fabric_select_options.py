# -*- coding: utf-8 -*-
from production_entry.production_planning.parent_fabric_options import repair_planning_child_table_metadata


def execute():
	"""Expand Parent Fabric Select options for Main / Loop bag chain labels."""
	repair_planning_child_table_metadata()
