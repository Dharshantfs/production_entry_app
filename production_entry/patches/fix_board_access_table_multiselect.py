# -*- coding: utf-8 -*-
"""Fix: convert allowed_units to Table MultiSelect, clean up broken custom fields."""
from production_entry.production_planning.board_access_fields import (
	ensure_board_access_multiselect_fields,
)


def execute():
	ensure_board_access_multiselect_fields()
