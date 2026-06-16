# -*- coding: utf-8 -*-
"""Retry multiselect fields using Frappe v16 field types (patch may have failed on MultiSelect)."""
from production_entry.production_planning.board_access_fields import (
	ensure_board_access_multiselect_fields,
)


def execute():
	ensure_board_access_multiselect_fields()
