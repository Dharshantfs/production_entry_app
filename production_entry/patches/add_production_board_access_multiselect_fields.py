# -*- coding: utf-8 -*-
"""Add multiselect board/unit fields on Production Board Access (keeps child DocTypes)."""
from production_entry.production_planning.board_access_fields import (
	ensure_board_access_multiselect_fields,
)


def execute():
	ensure_board_access_multiselect_fields()
