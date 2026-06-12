# -*- coding: utf-8 -*-
"""Re-apply Parent Fabric dedupe + Work Order editable (idempotent)."""
from production_entry.production_planning.parent_fabric_options import repair_planning_child_table_metadata


def execute():
	repair_planning_child_table_metadata()
