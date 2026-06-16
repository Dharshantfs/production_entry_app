# -*- coding: utf-8 -*-
"""Ensure board-access child tables have parent/idx columns (manual DocTypes often miss these)."""
from production_entry.production_planning.board_access_fields import (
	repair_board_access_child_table_columns,
)


def execute():
	repair_board_access_child_table_columns()
