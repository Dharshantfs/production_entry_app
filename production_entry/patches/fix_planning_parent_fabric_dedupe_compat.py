# -*- coding: utf-8 -*-
"""Re-run parent fabric dedupe after field_order compat fix (failed migrate retry)."""
from production_entry.production_planning.parent_fabric_options import repair_planning_child_table_metadata


def execute():
	repair_planning_child_table_metadata()
